"""FastAPI backend for ZhiYu."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import requests
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import (
    ALLOWED_ORIGINS,
    BASE_DIR,
    HUNYUAN_API_KEY,
    HUNYUAN_BASE_URL,
    HUNYUAN_MODEL,
)
from db import connect_db, ensure_default_session, init_db, insert_message, placeholder, using_postgres


app = FastAPI(title="ZhiYu API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5


class ChatRequest(BaseModel):
    query: str
    history: Optional[list[dict[str, Any]]] = None
    top_k: int = 5
    session_id: Optional[str] = "default"


UPLOAD_DIR = BASE_DIR / ".uploads" / "documents"
ALLOWED_DOCUMENT_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}
TEXT_FILE_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030")
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150

init_db()
db_conn = connect_db()
_retrieve_fn = None
_retrieve_import_error: Exception | None = None


def calc_credibility(similarity: float) -> str:
    if similarity >= 0.8:
        return "high"
    if similarity >= 0.5:
        return "medium"
    return "low"


def format_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted = []
    for chunk in chunks:
        similarity = float(chunk.get("similarity", 0.0) or 0.0)
        formatted.append(
            {
                "content": chunk.get("content", ""),
                "doc": chunk.get("doc", "unknown"),
                "similarity": similarity,
                "credibility": calc_credibility(similarity),
            }
        )
    return formatted


def parse_json_field(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


def parse_metadata_input(metadata: str | None) -> dict[str, Any]:
    if not metadata:
        return {}

    try:
        parsed = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="metadata must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return parsed


def normalize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def fetch_one_dict(cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))


def fetch_all_dicts(cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def serialize_document(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row.get("author"),
        "year": row.get("year"),
        "source_type": row.get("source_type"),
        "file_name": row.get("file_name"),
        "file_type": row.get("file_type"),
        "file_url": row.get("file_url"),
        "file_size": row.get("file_size"),
        "status": row.get("status"),
        "metadata": parse_json_field(row.get("metadata")) or {},
        "chunk_count": int(row.get("chunk_count") or 0),
        "created_at": normalize_timestamp(row.get("created_at")),
        "updated_at": normalize_timestamp(row.get("updated_at")),
    }


def serialize_document_chunk(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "chunk_index": row["chunk_index"],
        "content": row["content"],
        "page_start": row.get("page_start"),
        "page_end": row.get("page_end"),
        "section_title": row.get("section_title"),
        "char_start": row.get("char_start"),
        "char_end": row.get("char_end"),
        "source_title": row.get("source_title"),
        "embedding_id": row.get("embedding_id"),
        "metadata": parse_json_field(row.get("metadata")) or {},
        "created_at": normalize_timestamp(row.get("created_at")),
    }


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def merge_document_metadata(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def get_document_by_id(document_id: int) -> dict[str, Any] | None:
    mark = placeholder()
    cursor = db_conn.cursor()
    cursor.execute(
        f"""
        SELECT
            d.id,
            d.title,
            d.author,
            d.year,
            d.source_type,
            d.file_name,
            d.file_type,
            d.file_url,
            d.file_size,
            d.status,
            d.metadata,
            d.created_at,
            d.updated_at,
            COUNT(dc.id) AS chunk_count
        FROM documents d
        LEFT JOIN document_chunks dc ON dc.document_id = d.id
        WHERE d.id = {mark}
        GROUP BY d.id
        """,
        (document_id,),
    )
    return fetch_one_dict(cursor)


def update_document_file_url(document_id: int, file_url: str) -> None:
    mark = placeholder()
    db_conn.execute(
        f"UPDATE documents SET file_url = {mark}, updated_at = CURRENT_TIMESTAMP WHERE id = {mark}",
        (file_url, document_id),
    )


def update_document_record(
    document_id: int,
    *,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    status_value = status
    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else None

    if using_postgres():
        db_conn.execute(
            """
            UPDATE documents
            SET status = COALESCE(%s, status),
                metadata = COALESCE(%s::jsonb, metadata),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (status_value, metadata_json, document_id),
        )
        return

    db_conn.execute(
        """
        UPDATE documents
        SET status = COALESCE(?, status),
            metadata = COALESCE(?, metadata),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status_value, metadata_json, document_id),
    )


def insert_document_record(
    *,
    title: str,
    author: str | None,
    year: str | None,
    source_type: str | None,
    file_name: str,
    file_type: str,
    file_size: int,
    status: str,
    metadata: dict[str, Any],
) -> int:
    metadata_json = json.dumps(metadata, ensure_ascii=False)

    if using_postgres():
        cursor = db_conn.execute(
            """
            INSERT INTO documents (
                title, author, year, source_type, file_name, file_type,
                file_size, status, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (title, author, year, source_type, file_name, file_type, file_size, status, metadata_json),
        )
        return cursor.fetchone()[0]

    cursor = db_conn.execute(
        """
        INSERT INTO documents (
            title, author, year, source_type, file_name, file_type,
            file_size, status, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (title, author, year, source_type, file_name, file_type, file_size, status, metadata_json),
    )
    return cursor.lastrowid


def insert_document_chunks(document_id: int, chunks: list[dict[str, Any]]) -> None:
    mark = placeholder()
    db_conn.execute(f"DELETE FROM document_chunks WHERE document_id = {mark}", (document_id,))
    if not chunks:
        return

    if using_postgres():
        for chunk in chunks:
            db_conn.execute(
                """
                INSERT INTO document_chunks (
                    document_id,
                    chunk_index,
                    content,
                    page_start,
                    page_end,
                    section_title,
                    char_start,
                    char_end,
                    source_title,
                    metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    document_id,
                    chunk["chunk_index"],
                    chunk["content"],
                    chunk.get("page_start"),
                    chunk.get("page_end"),
                    chunk.get("section_title"),
                    chunk.get("char_start"),
                    chunk.get("char_end"),
                    chunk.get("source_title"),
                    json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                ),
            )
        return

    for chunk in chunks:
        db_conn.execute(
            """
            INSERT INTO document_chunks (
                document_id,
                chunk_index,
                content,
                page_start,
                page_end,
                section_title,
                char_start,
                char_end,
                source_title,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                chunk["chunk_index"],
                chunk["content"],
                chunk.get("page_start"),
                chunk.get("page_end"),
                chunk.get("section_title"),
                chunk.get("char_start"),
                chunk.get("char_end"),
                chunk.get("source_title"),
                json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
            ),
        )


def resolve_document_path(row: dict[str, Any]) -> Path | None:
    metadata = parse_json_field(row.get("metadata")) or {}
    storage_name = metadata.get("storage_name")
    if not storage_name:
        return None
    file_path = (UPLOAD_DIR / storage_name).resolve()
    upload_root = UPLOAD_DIR.resolve()
    if upload_root not in file_path.parents and file_path != upload_root:
        return None
    return file_path


def delete_document_assets(row: dict[str, Any]) -> None:
    mark = placeholder()
    db_conn.execute(f"DELETE FROM document_chunks WHERE document_id = {mark}", (row["id"],))
    db_conn.execute(f"DELETE FROM documents WHERE id = {mark}", (row["id"],))
    db_conn.commit()

    file_path = resolve_document_path(row)
    if file_path and file_path.exists():
        file_path.unlink()


def list_document_chunks(document_id: int, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    mark = placeholder()
    cursor = db_conn.cursor()
    cursor.execute(
        f"""
        SELECT
            id,
            document_id,
            chunk_index,
            content,
            page_start,
            page_end,
            section_title,
            char_start,
            char_end,
            source_title,
            embedding_id,
            metadata,
            created_at
        FROM document_chunks
        WHERE document_id = {mark}
        ORDER BY chunk_index ASC, id ASC
        LIMIT {mark} OFFSET {mark}
        """,
        (document_id, limit, offset),
    )
    return fetch_all_dicts(cursor)


def count_document_chunks(document_id: int) -> int:
    mark = placeholder()
    cursor = db_conn.cursor()
    cursor.execute(
        f"SELECT COUNT(*) FROM document_chunks WHERE document_id = {mark}",
        (document_id,),
    )
    row = cursor.fetchone()
    return int(row[0] or 0)


def read_text_file(path: Path) -> str:
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("unable to decode text file with supported encodings")


def extract_markdown_segments(path: Path) -> list[dict[str, Any]]:
    text = normalize_document_text(read_text_file(path))
    if not text:
        return []

    segments: list[dict[str, Any]] = []
    current_lines: list[str] = []
    current_title: str | None = None
    current_heading_level: int | None = None
    in_code_block = False

    def flush_current_section() -> None:
        nonlocal current_lines
        body = "\n".join(current_lines).strip()
        if not body:
            current_lines = []
            return
        segments.append(
            {
                "page_start": None,
                "page_end": None,
                "text": body,
                "section_title": current_title,
                "heading_level": current_heading_level,
                "segment_kind": "markdown_section",
            }
        )
        current_lines = []

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            current_lines.append(line)
            continue

        heading_match = None
        if not in_code_block:
            heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)

        if heading_match:
            flush_current_section()
            current_title = heading_match.group(2).strip()
            current_heading_level = len(heading_match.group(1))
            current_lines = [line]
            continue

        current_lines.append(line)

    flush_current_section()
    return segments


def extract_pdf_segments(path: Path) -> list[dict[str, Any]]:
    import fitz

    segments: list[dict[str, Any]] = []
    with fitz.open(path) as document:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text().strip()
            if text:
                segments.append({"page_start": page_index, "page_end": page_index, "text": text})
    return segments


def extract_docx_segments(path: Path) -> list[dict[str, Any]]:
    from docx import Document

    document = Document(path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()).strip()
    return [{"page_start": None, "page_end": None, "text": text}] if text else []


def extract_document_segments(path: Path, suffix: str) -> list[dict[str, Any]]:
    if suffix == ".md":
        return extract_markdown_segments(path)
    if suffix == ".txt":
        text = read_text_file(path).strip()
        return [{"page_start": None, "page_end": None, "text": text}] if text else []
    if suffix == ".pdf":
        return extract_pdf_segments(path)
    if suffix == ".docx":
        return extract_docx_segments(path)
    raise RuntimeError(f"unsupported parser for file type: {suffix}")


def normalize_document_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    lines = [line.rstrip() for line in text.split("\n")]
    collapsed = "\n".join(lines)
    while "\n\n\n" in collapsed:
        collapsed = collapsed.replace("\n\n\n", "\n\n")
    return collapsed.strip()


def build_chunks_for_segments(
    segments: list[dict[str, Any]],
    *,
    source_title: str,
    source_type: str | None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    global_offset = 0
    boundary_markers = [
        "\n\n",
        "\n",
        "## ",
        "# ",
        "```",
        "| ---",
        "|",
        "。",
        "！",
        "？",
        ". ",
        "! ",
        "? ",
        "; ",
    ]

    for segment in segments:
        raw_text = normalize_document_text(segment.get("text", ""))
        if not raw_text:
            continue

        segment_title = segment.get("section_title")
        segment_kind = segment.get("segment_kind") or ("page" if segment.get("page_start") else "document")
        segment_heading_level = segment.get("heading_level")
        text_length = len(raw_text)
        start = 0
        while start < text_length:
            target_end = min(start + chunk_size, text_length)
            end = target_end

            if target_end < text_length:
                window = raw_text[start:target_end]
                boundary = max(
                    window.rfind("\n\n"),
                    window.rfind("\n"),
                    window.rfind("。"),
                    window.rfind("！"),
                    window.rfind("？"),
                    window.rfind(". "),
                    window.rfind("; "),
                )
                boundary = max(window.rfind(marker) for marker in boundary_markers)
                if boundary >= int(chunk_size * 0.6):
                    end = start + boundary + 1

            chunk_text = raw_text[start:end].strip()
            if chunk_text:
                chunk_start = global_offset + start
                chunk_end = global_offset + end
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "content": chunk_text,
                        "page_start": segment.get("page_start"),
                        "page_end": segment.get("page_end"),
                        "section_title": segment_title,
                        "char_start": chunk_start,
                        "char_end": chunk_end,
                        "source_title": source_title,
                        "metadata": {
                            "source_type": source_type,
                            "segment_kind": segment_kind,
                            "heading_level": segment_heading_level,
                        },
                    }
                )

            if end >= text_length:
                break
            start = max(end - overlap, start + 1)

        global_offset += text_length + 2

    return chunks


def process_document(document_id: int) -> None:
    row = get_document_by_id(document_id)
    if row is None:
        raise RuntimeError("document not found for processing")

    file_path = resolve_document_path(row)
    if file_path is None or not file_path.exists():
        raise RuntimeError("uploaded file is missing")

    metadata = parse_json_field(row.get("metadata")) or {}
    suffix = Path(row["file_name"]).suffix.lower()
    segments = extract_document_segments(file_path, suffix)
    chunks = build_chunks_for_segments(
        segments,
        source_title=row["title"],
        source_type=row.get("source_type"),
    )
    if not chunks:
        raise RuntimeError("document text is empty after parsing")

    insert_document_chunks(document_id, chunks)
    updated_metadata = merge_document_metadata(
        metadata,
        {
            "parser": suffix.lstrip("."),
            "segment_count": len(segments),
            "chunk_count": len(chunks),
            "parse_error": None,
        },
    )
    update_document_record(document_id, status="parsed", metadata=updated_metadata)


def get_retrieve():
    global _retrieve_fn, _retrieve_import_error

    if _retrieve_fn is not None:
        return _retrieve_fn
    if _retrieve_import_error is not None:
        raise RuntimeError("Retrieval backend is unavailable") from _retrieve_import_error

    try:
        from api import retrieve as retrieve_fn
    except Exception as exc:
        _retrieve_import_error = exc
        print(f"[retrieve] import failed: {exc}")
        raise RuntimeError("Retrieval backend is unavailable") from exc

    _retrieve_fn = retrieve_fn
    return _retrieve_fn


def run_retrieval(query: str, top_k: int) -> list[dict[str, Any]]:
    try:
        retrieve = get_retrieve()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return retrieve(query, top_k)


def build_prompt(query: str, chunks: list[dict[str, Any]]) -> str:
    context = "\n\n".join(
        f"[Source {index + 1}] {chunk.get('doc', 'unknown')}\n{chunk.get('content', '')}"
        for index, chunk in enumerate(chunks)
    )
    return f"""You are ZhiYu, an academic assistant for architectural heritage research.
Answer only from the provided sources. If the sources do not contain enough
information, say so clearly. Cite the source titles used in your answer.

Sources:
{context}

User question:
{query}
"""


def chat_with_hunyuan(prompt: str) -> str:
    api_key = HUNYUAN_API_KEY.strip()
    if not api_key:
        return "LLM is not configured. Please set HUNYUAN_API_KEY in .env."

    try:
        url = f"{HUNYUAN_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": HUNYUAN_MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[Hunyuan] call failed: {exc}")
        return f"LLM call failed: {exc}"


def save_message(session_id: str, role: str, content: str, sources: str) -> None:
    mark = placeholder()
    db_conn.execute(
        "INSERT INTO conversations (session_id, role, content, sources) "
        f"VALUES ({mark}, {mark}, {mark}, {mark})",
        (session_id, role, content, sources),
    )
    structured_session_id = ensure_default_session(db_conn, session_id)
    insert_message(db_conn, structured_session_id, role, content, sources)
    db_conn.commit()


@app.post("/api/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    year: str | None = Form(None),
    source_type: str | None = Form(None),
    metadata: str | None = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="file name is required")

    original_name = Path(file.filename).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_DOCUMENT_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type: {suffix or 'unknown'}",
        )

    ensure_upload_dir()
    storage_name = f"{uuid4().hex}{suffix}"
    storage_path = UPLOAD_DIR / storage_name
    metadata_payload = parse_metadata_input(metadata)
    document_title = (title or Path(original_name).stem).strip()
    if not document_title:
        raise HTTPException(status_code=400, detail="title is required")

    try:
        with storage_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)
    finally:
        file.file.close()

    metadata_payload.update(
        {
            "content_type": file.content_type,
            "storage_name": storage_name,
            "original_file_name": original_name,
        }
    )

    try:
        document_id = insert_document_record(
            title=document_title,
            author=(author or "").strip() or None,
            year=(year or "").strip() or None,
            source_type=(source_type or "").strip() or None,
            file_name=original_name,
            file_type=suffix.lstrip(".").upper(),
            file_size=storage_path.stat().st_size,
            status="processing",
            metadata=metadata_payload,
        )
        file_url = f"/api/documents/{document_id}/file"
        update_document_file_url(document_id, file_url)
        db_conn.commit()
    except Exception:
        db_conn.rollback()
        if storage_path.exists():
            storage_path.unlink()
        raise

    try:
        process_document(document_id)
        db_conn.commit()
    except Exception as exc:
        db_conn.rollback()
        failure_row = get_document_by_id(document_id)
        failure_metadata = parse_json_field(failure_row.get("metadata")) if failure_row else metadata_payload
        update_document_record(
            document_id,
            status="failed",
            metadata=merge_document_metadata(
                failure_metadata or {},
                {
                    "parse_error": str(exc),
                    "chunk_count": 0,
                },
            ),
        )
        db_conn.commit()

    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=500, detail="document record was not created")
    return {"document": serialize_document(row)}


@app.get("/api/documents")
def list_documents():
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT
            d.id,
            d.title,
            d.author,
            d.year,
            d.source_type,
            d.file_name,
            d.file_type,
            d.file_url,
            d.file_size,
            d.status,
            d.metadata,
            d.created_at,
            d.updated_at,
            COUNT(dc.id) AS chunk_count
        FROM documents d
        LEFT JOIN document_chunks dc ON dc.document_id = d.id
        GROUP BY d.id
        ORDER BY d.created_at DESC, d.id DESC
        """
    )
    return {"documents": [serialize_document(row) for row in fetch_all_dicts(cursor)]}


@app.get("/api/documents/{document_id}")
def get_document(document_id: int):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {"document": serialize_document(row)}


@app.get("/api/documents/{document_id}/chunks")
def get_document_chunks(document_id: int, limit: int = 200, offset: int = 0):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be 0 or greater")

    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    total = count_document_chunks(document_id)
    chunks = list_document_chunks(document_id, limit=limit, offset=offset)
    return {
        "document": serialize_document(row),
        "chunks": [serialize_document_chunk(chunk) for chunk in chunks],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "returned": len(chunks),
        },
    }


@app.get("/api/documents/{document_id}/file")
def get_document_file(document_id: int):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    file_path = resolve_document_path(row)
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="file not found")

    return FileResponse(path=file_path, filename=row.get("file_name"))


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: int):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    delete_document_assets(row)
    return {"ok": True, "deleted_document_id": document_id}


@app.post("/api/retrieve")
def api_retrieve(req: RetrieveRequest):
    chunks = run_retrieval(req.query, req.top_k)
    return {"chunks": format_chunks(chunks)}


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    chunks = run_retrieval(req.query, req.top_k)

    if chunks:
        prompt = build_prompt(req.query, chunks)
        answer = chat_with_hunyuan(prompt)
    else:
        answer = "No relevant sources were found. Please try another question."

    session_id = req.session_id or "default"
    formatted_chunks = format_chunks(chunks)
    save_message(session_id, "user", req.query, "")
    save_message(
        session_id,
        "assistant",
        answer,
        json.dumps(formatted_chunks, ensure_ascii=False),
    )

    return {"answer": answer, "chunks": formatted_chunks, "session_id": session_id}


@app.get("/api/history")
def get_history(session_id: str = "default", limit: int = 20):
    mark = placeholder()
    cursor = db_conn.cursor()
    cursor.execute(
        "SELECT role, content, sources, timestamp FROM conversations "
        f"WHERE session_id = {mark} ORDER BY timestamp DESC LIMIT {mark}",
        (session_id, limit),
    )
    rows = cursor.fetchall()
    return [
        {
            "role": row[0],
            "content": row[1],
            "sources": json.loads(row[2]) if row[2] else [],
            "timestamp": str(row[3]),
        }
        for row in reversed(rows)
    ]


@app.get("/health")
def health():
    cursor = db_conn.cursor()
    cursor.execute("SELECT 1")
    cursor.fetchone()
    return {
        "status": "ok",
        "database": "postgres" if using_postgres() else "sqlite",
    }


if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
