"""FastAPI backend for ZhiYu."""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote
from uuid import uuid4

import requests
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from config import (
    ALLOWED_ORIGINS,
    ALLOWED_ORIGIN_REGEX,
    BASE_DIR,
    HUNYUAN_API_KEY,
    HUNYUAN_BASE_URL,
    HUNYUAN_MODEL,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_STORAGE_BUCKET,
    SUPABASE_STORAGE_PREFIX,
    SUPABASE_STORAGE_PUBLIC,
    SUPABASE_STORAGE_TIMEOUT,
    SUPABASE_URL,
    USE_SUPABASE_STORAGE,
)
from db import connect_db, ensure_default_session, init_db, insert_message, placeholder, using_postgres
from embeddings import EMBEDDING_BATCH_SIZE, EMBEDDING_MODEL, embed_texts, embedding_status, embeddings_configured


app = FastAPI(title="ZhiYu API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    document_id: Optional[int] = None


class ChatRequest(BaseModel):
    query: str
    history: Optional[list[dict[str, Any]]] = None
    top_k: int = 5
    session_id: Optional[str] = "default"
    document_id: Optional[int] = None


class ResearchAgentRequest(ChatRequest):
    pass


class TextDocumentRequest(BaseModel):
    title: str
    content: str
    author: Optional[str] = None
    year: Optional[str] = None
    source_type: Optional[str] = "text_input"
    metadata: Optional[dict[str, Any]] = None


class DocumentMetadataUpdate(BaseModel):
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    keywords: Optional[list[str]] = None


UPLOAD_DIR = BASE_DIR / ".uploads" / "documents"
ALLOWED_DOCUMENT_SUFFIXES = {".pdf", ".txt", ".md", ".docx"}
TEXT_FILE_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030")
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150
PDF_OCR_MIN_QUALITY = 120
PDF_OCR_MAX_PAGES = 40
MOJIBAKE_MARKERS = (
    "Ã",
    "Â",
    "Ä",
    "Å",
    "Æ",
    "Ç",
    "È",
    "É",
    "ä",
    "å",
    "æ",
    "ç",
    "è",
    "é",
    "浣",
    "犲",
    "鍩",
    "鏂",
    "銆",
    "锛",
    "绱",
    "閿",
    "�",
)
MOJIBAKE_CONTROL_RANGES = ((0x80, 0x9F),)
LATIN1_ARTIFACT_RANGES = ((0x00C0, 0x00FF),)

# ---------------------------------------------------------------------------
# 数据库连接：惰性初始化 + 断线自愈
#
# 以前这里是模块顶层的 `init_db()` 和 `db_conn = connect_db()`。
# 只要数据库连不上，import 阶段就抛异常，整个进程启动失败 ——
# 于是连不依赖数据库的接口（比如 /health）都返回 503，用户只能看到
# 前端那句 "Unexpected token 'Y' ... is not valid JSON"。
#
# 改成代理对象之后：服务先正常启动，只有真正访问数据库的请求才会失败，
# 而且数据库恢复后无需重启，下一个请求会自动连上。
# ---------------------------------------------------------------------------

_CONNECTION_ERROR_MARKERS = ("closed", "not open", "terminating")


def _is_connection_error(exc: BaseException) -> bool:
    """判断异常是否属于「连接断了、重连即可」这一类。"""
    if using_postgres():
        try:
            import psycopg
        except ImportError:
            return False
        return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))
    if isinstance(exc, sqlite3.ProgrammingError):
        return any(marker in str(exc).lower() for marker in _CONNECTION_ERROR_MARKERS)
    return False


class _LazyDbConnection:
    """数据库连接代理：第一次用到时才连接，连接失效后自动重连。"""

    def __init__(self) -> None:
        self._conn = None
        self._error: str | None = None
        self._initialized = False
        self._lock = threading.Lock()

    def _is_alive(self, conn) -> bool:
        try:
            if using_postgres():
                return not conn.closed
            return True
        except Exception:
            return False

    def _connection(self):
        with self._lock:
            if self._conn is not None and self._is_alive(self._conn):
                return self._conn
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            try:
                if not self._initialized:
                    init_db()
                    self._initialized = True
                self._conn = connect_db()
                self._error = None
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
                raise HTTPException(
                    status_code=503,
                    detail=f"数据库暂时不可用：{self._error}",
                ) from exc
            return self._conn

    def _call(self, name: str, *args, **kwargs):
        conn = self._connection()
        try:
            return getattr(conn, name)(*args, **kwargs)
        except Exception as exc:
            if _is_connection_error(exc):
                # 丢弃坏连接，下一个请求会自动重连
                self.reset()
            raise

    def reset(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = None
            self._error = None

    def status(self) -> str:
        """健康检查用：主动探一次，返回 'ok' 或具体错误描述。"""
        try:
            cursor = self._connection().cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return "ok"
        except HTTPException:
            return self._error or "unavailable"
        except Exception as exc:
            self.reset()
            return f"{type(exc).__name__}: {exc}"

    def execute(self, *args, **kwargs):
        return self._call("execute", *args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._call("executemany", *args, **kwargs)

    def cursor(self, *args, **kwargs):
        return self._call("cursor", *args, **kwargs)

    def commit(self, *args, **kwargs):
        return self._call("commit", *args, **kwargs)

    def rollback(self, *args, **kwargs):
        return self._call("rollback", *args, **kwargs)

    def close(self, *args, **kwargs):
        return self._call("close", *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._connection(), name)


db_conn = _LazyDbConnection()
_retrieve_fn = None
_retrieve_import_error: Exception | None = None


def calc_credibility(similarity: float) -> str:
    if similarity >= 0.8:
        return "high"
    if similarity >= 0.5:
        return "medium"
    return "low"


def is_mojibake_like(value: str | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    marker_hits = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    latin1_artifact_hits = sum(1 for char in text if "\u00c0" <= char <= "\u00ff")
    control_hits = sum(
        1
        for char in text
        if any(start <= ord(char) <= end for start, end in MOJIBAKE_CONTROL_RANGES)
    )
    ascii_count = sum(1 for char in text if char.isascii())
    cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    replacement_hits = text.count("\ufffd")
    return (
        marker_hits >= 2
        or latin1_artifact_hits >= 2
        or control_hits > 0
        or replacement_hits > 0
        or (marker_hits >= 1 and cjk_count < 4)
        or (ascii_count == 0 and "?" in text)
    )


def has_latin1_artifacts(text: str) -> bool:
    return any(
        start <= ord(char) <= end
        for char in text
        for start, end in LATIN1_ARTIFACT_RANGES
    )


def clean_citation_text(value: str | None, fallback: str | None = None) -> str | None:
    text = repair_mojibake_text(value).strip()
    if not text or is_mojibake_like(text):
        fallback_text = repair_mojibake_text(fallback).strip()
        return fallback_text if fallback_text and not is_mojibake_like(fallback_text) else None
    return text


def format_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted = []
    for chunk in chunks:
        similarity = float(chunk.get("similarity", 0.0) or 0.0)
        clean_doc = clean_citation_text(chunk.get("doc"), "Unknown source") or "Unknown source"
        clean_section = clean_citation_text(chunk.get("section_title"))
        if clean_section and clean_section in clean_doc:
            clean_section = None
        formatted.append(
            {
                "content": repair_mojibake_text(chunk.get("content", "")),
                "doc": clean_doc,
                "similarity": similarity,
                "credibility": calc_credibility(similarity),
                "document_id": chunk.get("document_id"),
                "provider": chunk.get("provider"),
                "embedding_model": chunk.get("embedding_model"),
                "embedding_score": chunk.get("embedding_score"),
                "keyword_score": chunk.get("keyword_score"),
                "coverage_score": chunk.get("coverage_score"),
                "title_score": chunk.get("title_score"),
                "section_score": chunk.get("section_score"),
                "length_quality": chunk.get("length_quality"),
                "rerank_score": chunk.get("rerank_score"),
                "source_type": chunk.get("source_type"),
                "section_title": clean_section,
                "chunk_index": chunk.get("chunk_index"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
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
    metadata = parse_json_field(row.get("metadata")) or {}
    if "original_file_name" in metadata:
        metadata["original_file_name"] = repair_mojibake_text(metadata.get("original_file_name"))
    return {
        "id": row["id"],
        "title": repair_mojibake_text(row["title"]),
        "author": row.get("author"),
        "year": row.get("year"),
        "source_type": row.get("source_type"),
        "file_name": repair_mojibake_text(row.get("file_name")),
        "file_type": row.get("file_type"),
        "file_url": row.get("file_url"),
        "file_size": row.get("file_size"),
        "status": row.get("status"),
        "metadata": metadata,
        "chunk_count": int(row.get("chunk_count") or 0),
        "created_at": normalize_timestamp(row.get("created_at")),
        "updated_at": normalize_timestamp(row.get("updated_at")),
    }


def serialize_document_chunk(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "document_id": row["document_id"],
        "chunk_index": row["chunk_index"],
        "content": repair_mojibake_text(row["content"]),
        "page_start": row.get("page_start"),
        "page_end": row.get("page_end"),
        "section_title": clean_text_value(row.get("section_title")),
        "char_start": row.get("char_start"),
        "char_end": row.get("char_end"),
        "source_title": clean_text_value(row.get("source_title")),
        "embedding_id": row.get("embedding_id"),
        "embedding_model": row.get("embedding_model"),
        "has_embedding": bool(row.get("embedding")),
        "metadata": parse_json_field(row.get("metadata")) or {},
        "created_at": normalize_timestamp(row.get("created_at")),
    }


def serialize_retrieval_log(row: dict[str, Any]) -> dict[str, Any]:
    metadata = parse_json_field(row.get("metadata")) or {}
    return {
        "id": row["id"],
        "session_id": row.get("session_id"),
        "message_id": row.get("message_id"),
        "query": row["query"],
        "provider": row.get("provider"),
        "top_k": row.get("top_k"),
        "results": parse_json_field(row.get("results")) or [],
        "latency_ms": row.get("latency_ms"),
        "success": bool(row.get("success")),
        "error": row.get("error"),
        "metadata": metadata,
        "created_at": normalize_timestamp(row.get("created_at")),
    }


def ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def supabase_storage_configured() -> bool:
    return bool(
        USE_SUPABASE_STORAGE
        and SUPABASE_URL
        and SUPABASE_SERVICE_ROLE_KEY
        and SUPABASE_STORAGE_BUCKET
    )


def supabase_storage_missing_config() -> list[str]:
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not SUPABASE_STORAGE_BUCKET:
        missing.append("SUPABASE_STORAGE_BUCKET")
    return missing


def require_supabase_storage_if_enabled() -> None:
    if not USE_SUPABASE_STORAGE:
        return

    missing = supabase_storage_missing_config()
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase Storage is enabled but missing: {', '.join(missing)}",
        )


def supabase_storage_headers(content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def supabase_storage_object_path(storage_name: str) -> str:
    cleaned_name = storage_name.strip("/").replace("\\", "/")
    if not SUPABASE_STORAGE_PREFIX:
        return cleaned_name
    return f"{SUPABASE_STORAGE_PREFIX}/{cleaned_name}".strip("/")


def supabase_storage_object_url(object_path: str, *, public: bool | None = None) -> str:
    visibility = SUPABASE_STORAGE_PUBLIC if public is None else public
    public_part = "/public" if visibility else ""
    encoded_path = quote(object_path.strip("/"), safe="/")
    return f"{SUPABASE_URL}/storage/v1/object{public_part}/{SUPABASE_STORAGE_BUCKET}/{encoded_path}"


def upload_file_to_supabase_storage(
    *,
    file_path: Path,
    storage_name: str,
    content_type: str | None,
) -> dict[str, str]:
    if not supabase_storage_configured():
        raise RuntimeError("Supabase Storage is not configured")

    object_path = supabase_storage_object_path(storage_name)
    guessed_type = content_type or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    response = requests.post(
        supabase_storage_object_url(object_path, public=False),
        headers={
            **supabase_storage_headers(guessed_type),
            "x-upsert": "true",
        },
        data=file_path.read_bytes(),
        timeout=SUPABASE_STORAGE_TIMEOUT,
    )
    if response.status_code not in (200, 201):
        print(
            "[storage] upload failed "
            f"bucket={SUPABASE_STORAGE_BUCKET} path={object_path} "
            f"status={response.status_code} body={response.text[:500]}"
        )
        raise RuntimeError(f"Supabase Storage upload failed: {response.status_code} {response.text}")

    return {
        "provider": "supabase_storage",
        "bucket": SUPABASE_STORAGE_BUCKET,
        "path": object_path,
        "url": supabase_storage_object_url(object_path),
        "public_url": supabase_storage_object_url(object_path, public=True),
    }


def test_supabase_storage_write() -> dict[str, Any]:
    if not supabase_storage_configured():
        raise RuntimeError("Supabase Storage is not configured")

    object_path = supabase_storage_object_path(f"_healthcheck/{uuid4().hex}.txt")
    response = requests.post(
        supabase_storage_object_url(object_path, public=False),
        headers={
            **supabase_storage_headers("text/plain; charset=utf-8"),
            "x-upsert": "true",
        },
        data=b"zhiyu storage healthcheck",
        timeout=SUPABASE_STORAGE_TIMEOUT,
    )
    ok = response.status_code in (200, 201)
    result = {
        "ok": ok,
        "status_code": response.status_code,
        "bucket": SUPABASE_STORAGE_BUCKET,
        "path": object_path,
        "body": response.text[:500],
    }
    if ok:
        try:
            delete_supabase_storage_file(object_path)
            result["cleanup"] = "deleted"
        except Exception as exc:
            result["cleanup"] = f"failed: {exc}"
    return result


def download_supabase_storage_file(object_path: str, target_path: Path | None = None) -> bytes:
    response = requests.get(
        supabase_storage_object_url(object_path, public=False),
        headers=supabase_storage_headers(),
        timeout=SUPABASE_STORAGE_TIMEOUT,
    )
    if response.status_code == 404:
        raise FileNotFoundError("Supabase Storage object not found")
    if response.status_code != 200:
        raise RuntimeError(f"Supabase Storage download failed: {response.status_code} {response.text}")

    data = response.content
    if target_path is not None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(data)
    return data


def delete_supabase_storage_file(object_path: str) -> None:
    if not supabase_storage_configured():
        return

    response = requests.delete(
        f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}",
        headers=supabase_storage_headers("application/json"),
        json={"prefixes": [object_path.strip("/")]},
        timeout=SUPABASE_STORAGE_TIMEOUT,
    )
    if response.status_code not in (200, 204):
        raise RuntimeError(f"Supabase Storage delete failed: {response.status_code} {response.text}")


def merge_document_metadata(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def mojibake_score(text: str) -> int:
    if not text:
        return 0
    marker_score = sum(text.count(marker) for marker in MOJIBAKE_MARKERS) * 8
    replacement_score = text.count("\ufffd") * 20
    control_score = sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t") * 10
    c1_control_score = sum(
        1
        for char in text
        if any(start <= ord(char) <= end for start, end in MOJIBAKE_CONTROL_RANGES)
    ) * 12
    latin_mojibake_score = len(re.findall(r"[ÃÂÄÅÆÇÈÉäåæçèé][\x80-\xbf\u0080-\u00bf]?", text)) * 8
    latin1_artifact_score = sum(
        1
        for char in text
        if any(start <= ord(char) <= end for start, end in LATIN1_ARTIFACT_RANGES)
    ) * 6
    return (
        marker_score
        + replacement_score
        + control_score
        + c1_control_score
        + latin_mojibake_score
        + latin1_artifact_score
    )


def readable_text_score(text: str) -> int:
    cjk_score = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    ascii_score = sum(1 for char in text if char.isascii() and char.isalnum())
    punctuation_score = sum(1 for char in text if char in "，。！？；：（）《》、“”")
    return cjk_score * 3 + ascii_score + punctuation_score


def decode_mojibake_candidate(text: str, encoding: str) -> str | None:
    try:
        return text.encode(encoding).decode("utf-8")
    except UnicodeError:
        try:
            return text.encode(encoding).decode("utf-8", errors="replace")
        except UnicodeError:
            return None


def repair_mojibake_text(text: str | None) -> str:
    if not text:
        return ""

    candidates = [text]
    try:
        from ftfy import fix_text
    except Exception:
        fix_text = None

    if fix_text is not None:
        fixed = fix_text(text)
        if fixed and fixed not in candidates:
            candidates.append(fixed)

    encodings = ("latin1", "cp1252", "gb18030") if has_latin1_artifacts(text) else ("gb18030",)
    for encoding in encodings:
        for source in list(candidates):
            candidate = decode_mojibake_candidate(source, encoding)
            if candidate and candidate not in candidates:
                candidates.append(candidate)
                if fix_text is not None:
                    fixed_candidate = fix_text(candidate)
                    if fixed_candidate and fixed_candidate not in candidates:
                        candidates.append(fixed_candidate)

    def rank(candidate: str) -> tuple[int, int, int]:
        return (
            -mojibake_score(candidate),
            readable_text_score(candidate),
            -abs(len(candidate) - len(text)),
        )

    return max(candidates, key=rank)


def clean_text_value(value: str | None) -> str | None:
    cleaned = repair_mojibake_text(value).strip()
    return cleaned or None


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


def update_document_text_fields(
    document_id: int,
    *,
    title: str | None,
    author: str | None,
    source_type: str | None,
) -> None:
    mark = placeholder()
    db_conn.execute(
        f"""
        UPDATE documents
        SET title = COALESCE({mark}, title),
            author = {mark},
            source_type = {mark},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = {mark}
        """,
        (title, author, source_type, document_id),
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


def store_document_file_blob(
    document_id: int,
    *,
    file_name: str,
    content_type: str | None,
    file_path: Path,
) -> None:
    mark = placeholder()
    file_bytes = file_path.read_bytes()
    if using_postgres():
        db_conn.execute(
            """
            INSERT INTO document_files (document_id, file_name, content_type, file_size, data)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                file_name = EXCLUDED.file_name,
                content_type = EXCLUDED.content_type,
                file_size = EXCLUDED.file_size,
                data = EXCLUDED.data
            """,
            (document_id, file_name, content_type, len(file_bytes), file_bytes),
        )
        return

    db_conn.execute(
        f"""
        INSERT OR REPLACE INTO document_files (document_id, file_name, content_type, file_size, data)
        VALUES ({mark}, {mark}, {mark}, {mark}, {mark})
        """,
        (document_id, file_name, content_type, len(file_bytes), file_bytes),
    )


def insert_document_chunks(document_id: int, chunks: list[dict[str, Any]], *, repair_text: bool = True) -> None:
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
                    repair_mojibake_text(chunk["content"]) if repair_text else chunk["content"],
                    chunk.get("page_start"),
                    chunk.get("page_end"),
                    clean_text_value(chunk.get("section_title")) if repair_text else chunk.get("section_title"),
                    chunk.get("char_start"),
                    chunk.get("char_end"),
                    clean_text_value(chunk.get("source_title")) if repair_text else chunk.get("source_title"),
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
                repair_mojibake_text(chunk["content"]) if repair_text else chunk["content"],
                chunk.get("page_start"),
                chunk.get("page_end"),
                clean_text_value(chunk.get("section_title")) if repair_text else chunk.get("section_title"),
                chunk.get("char_start"),
                chunk.get("char_end"),
                clean_text_value(chunk.get("source_title")) if repair_text else chunk.get("source_title"),
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
    if not file_path.exists():
        storage_provider = metadata.get("storage_provider")
        storage_path = metadata.get("storage_path")
        if storage_provider == "supabase_storage" and storage_path:
            try:
                download_supabase_storage_file(str(storage_path), file_path)
            except FileNotFoundError:
                return file_path
        else:
            restore_document_file_from_blob(row["id"], file_path)
    return file_path


def restore_document_file_from_blob(document_id: int, target_path: Path) -> bool:
    mark = placeholder()
    cursor = db_conn.cursor()
    cursor.execute(
        f"SELECT data FROM document_files WHERE document_id = {mark}",
        (document_id,),
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return False

    data = row[0]
    if isinstance(data, memoryview):
        data = data.tobytes()
    elif not isinstance(data, bytes):
        data = bytes(data)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)
    return True


def delete_document_assets(row: dict[str, Any]) -> None:
    metadata = parse_json_field(row.get("metadata")) or {}
    file_path = None
    storage_name = metadata.get("storage_name")
    if storage_name:
        candidate_path = (UPLOAD_DIR / storage_name).resolve()
        upload_root = UPLOAD_DIR.resolve()
        if upload_root in candidate_path.parents or candidate_path == upload_root:
            file_path = candidate_path
    if metadata.get("storage_provider") == "supabase_storage" and metadata.get("storage_path"):
        delete_supabase_storage_file(str(metadata["storage_path"]))

    mark = placeholder()
    db_conn.execute(f"DELETE FROM document_citations WHERE document_id = {mark}", (row["id"],))
    db_conn.execute(f"DELETE FROM document_chunks WHERE document_id = {mark}", (row["id"],))
    db_conn.execute(f"DELETE FROM document_files WHERE document_id = {mark}", (row["id"],))
    db_conn.execute(f"DELETE FROM documents WHERE id = {mark}", (row["id"],))
    db_conn.commit()

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
            embedding,
            embedding_model,
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


def list_document_chunks_for_embedding(document_id: int, *, force: bool = False) -> list[dict[str, Any]]:
    mark = placeholder()
    cursor = db_conn.cursor()
    if force:
        cursor.execute(
            f"""
            SELECT id, content
            FROM document_chunks
            WHERE document_id = {mark}
            ORDER BY chunk_index ASC, id ASC
            """,
            (document_id,),
        )
    else:
        cursor.execute(
            f"""
            SELECT id, content
            FROM document_chunks
            WHERE document_id = {mark}
              AND (embedding IS NULL OR embedding_model IS NULL OR embedding_model <> {mark})
            ORDER BY chunk_index ASC, id ASC
            """,
            (document_id, EMBEDDING_MODEL),
        )
    return fetch_all_dicts(cursor)


def update_chunk_embedding(chunk_id: int, embedding: list[float]) -> None:
    mark = placeholder()
    embedding_json = json.dumps(embedding)
    if using_postgres():
        db_conn.execute(
            """
            UPDATE document_chunks
            SET embedding = %s::jsonb,
                embedding_model = %s,
                embedding_updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (embedding_json, EMBEDDING_MODEL, chunk_id),
        )
        return

    db_conn.execute(
        f"""
        UPDATE document_chunks
        SET embedding = {mark},
            embedding_model = {mark},
            embedding_updated_at = CURRENT_TIMESTAMP
        WHERE id = {mark}
        """,
        (embedding_json, EMBEDDING_MODEL, chunk_id),
    )


def build_document_embeddings(document_id: int, *, force: bool = False) -> dict[str, Any]:
    if not embeddings_configured():
        raise RuntimeError("Embedding retrieval is not configured")

    row = get_document_by_id(document_id)
    if row is None:
        raise RuntimeError("document not found")

    chunks = list_document_chunks_for_embedding(document_id, force=force)
    embedded_count = 0
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
        vectors = embed_texts([chunk["content"] for chunk in batch])
        for chunk, vector in zip(batch, vectors):
            update_chunk_embedding(chunk["id"], vector)
            embedded_count += 1

    return {
        "document_id": document_id,
        "model": EMBEDDING_MODEL,
        "force": force,
        "selected_chunks": len(chunks),
        "embedded_chunks": embedded_count,
    }


def try_build_document_embeddings(document_id: int, *, force: bool = False) -> dict[str, Any] | None:
    if not embeddings_configured():
        return None

    try:
        result = build_document_embeddings(document_id, force=force)
        update_document_record(
            document_id,
            metadata=merge_document_metadata(
                parse_json_field((get_document_by_id(document_id) or {}).get("metadata")) or {},
                {
                    "embedding_model": result.get("model"),
                    "embedded_chunks": result.get("embedded_chunks"),
                    "embedding_error": None,
                },
            ),
        )
        return result
    except Exception as exc:
        update_document_record(
            document_id,
            metadata=merge_document_metadata(
                parse_json_field((get_document_by_id(document_id) or {}).get("metadata")) or {},
                {
                    "embedding_model": EMBEDDING_MODEL,
                    "embedding_error": str(exc),
                },
            ),
        )
        print(f"[documents] embedding build skipped for document {document_id}: {exc}")
        return None


def embedding_counts() -> dict[str, int]:
    cursor = db_conn.cursor()
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total_chunks,
            SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_chunks
        FROM document_chunks
        """
    )
    row = fetch_one_dict(cursor) or {}
    return {
        "total_chunks": int(row.get("total_chunks") or 0),
        "embedded_chunks": int(row.get("embedded_chunks") or 0),
    }


def insert_retrieval_log(
    *,
    session_id: int | None,
    query: str,
    provider: str,
    top_k: int,
    results: list[dict[str, Any]],
    latency_ms: int,
    success: bool,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    results_json = json.dumps(results, ensure_ascii=False)
    error_value = error or None
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)

    if using_postgres():
        cursor = db_conn.execute(
            """
            INSERT INTO retrieval_logs (
                session_id, message_id, query, provider, top_k, results, latency_ms, success, error, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (session_id, None, query, provider, top_k, results_json, latency_ms, success, error_value, metadata_json),
        )
        return cursor.fetchone()[0]

    cursor = db_conn.execute(
        """
        INSERT INTO retrieval_logs (
            session_id, message_id, query, provider, top_k, results, latency_ms, success, error, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, None, query, provider, top_k, results_json, latency_ms, success, error_value, metadata_json),
    )
    return cursor.lastrowid


def find_document_chunk_id(document_id: int, chunk_index: int | None) -> int | None:
    if chunk_index is None:
        return None

    mark = placeholder()
    cursor = db_conn.cursor()
    cursor.execute(
        f"""
        SELECT id
        FROM document_chunks
        WHERE document_id = {mark}
          AND chunk_index = {mark}
        ORDER BY id ASC
        LIMIT 1
        """,
        (document_id, chunk_index),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def insert_document_citations(
    *,
    session_id: int | None,
    retrieval_log_id: int | None,
    chunks: list[dict[str, Any]],
) -> None:
    if not chunks:
        return

    for index, chunk in enumerate(chunks, start=1):
        document_id = chunk.get("document_id")
        if document_id is None:
            continue

        try:
            document_id_value = int(document_id)
        except (TypeError, ValueError):
            continue

        chunk_index = chunk.get("chunk_index")
        try:
            chunk_index_value = int(chunk_index) if chunk_index is not None else None
        except (TypeError, ValueError):
            chunk_index_value = None

        chunk_id = find_document_chunk_id(document_id_value, chunk_index_value)
        metadata_json = json.dumps(
            {
                "provider": chunk.get("provider"),
                "similarity": chunk.get("similarity"),
                "credibility": chunk.get("credibility"),
                "embedding_model": chunk.get("embedding_model"),
                "embedding_score": chunk.get("embedding_score"),
                "keyword_score": chunk.get("keyword_score"),
                "rerank_score": chunk.get("rerank_score"),
            },
            ensure_ascii=False,
        )

        if using_postgres():
            db_conn.execute(
                """
                INSERT INTO document_citations (
                    session_id,
                    message_id,
                    retrieval_log_id,
                    document_id,
                    chunk_id,
                    chunk_index,
                    source_label,
                    source_title,
                    page_start,
                    page_end,
                    metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    session_id,
                    None,
                    retrieval_log_id,
                    document_id_value,
                    chunk_id,
                    chunk_index_value,
                    f"Source {index}",
                    chunk.get("doc"),
                    chunk.get("page_start"),
                    chunk.get("page_end"),
                    metadata_json,
                ),
            )
            continue

        db_conn.execute(
            """
            INSERT INTO document_citations (
                session_id,
                message_id,
                retrieval_log_id,
                document_id,
                chunk_id,
                chunk_index,
                source_label,
                source_title,
                page_start,
                page_end,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                None,
                retrieval_log_id,
                document_id_value,
                chunk_id,
                chunk_index_value,
                f"Source {index}",
                chunk.get("doc"),
                chunk.get("page_start"),
                chunk.get("page_end"),
                metadata_json,
            ),
        )


def list_retrieval_logs(*, limit: int = 50, session_id: int | None = None) -> list[dict[str, Any]]:
    mark = placeholder()
    cursor = db_conn.cursor()
    if session_id is None:
        cursor.execute(
            f"""
            SELECT id, session_id, message_id, query, provider, top_k, results, latency_ms, success, error, metadata, created_at
            FROM retrieval_logs
            ORDER BY created_at DESC, id DESC
            LIMIT {mark}
            """,
            (limit,),
        )
    else:
        cursor.execute(
            f"""
            SELECT id, session_id, message_id, query, provider, top_k, results, latency_ms, success, error, metadata, created_at
            FROM retrieval_logs
            WHERE session_id = {mark}
            ORDER BY created_at DESC, id DESC
            LIMIT {mark}
            """,
            (session_id, limit),
        )
    return fetch_all_dicts(cursor)


def read_text_file(path: Path) -> str:
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("unable to decode text file with supported encodings")


def text_segments_quality(segments: list[dict[str, Any]]) -> int:
    score = 0
    for segment in segments:
        text = repair_mojibake_text(segment.get("text", ""))
        score += readable_text_score(text)
        score -= mojibake_score(text) * 2
    return score


def extract_pdf_segments_with_ocr(path: Path, *, max_pages: int | None = None) -> list[dict[str, Any]]:
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except Exception as exc:
        print(f"[documents] OCR unavailable: {exc}")
        return []

    segments: list[dict[str, Any]] = []
    with fitz.open(path) as document:
        page_limit = max_pages if max_pages is not None else PDF_OCR_MAX_PAGES
        page_count = min(len(document), page_limit)
        for page_index in range(page_count):
            page = document[page_index]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            text = pytesseract.image_to_string(image, lang="chi_sim+eng").strip()
            if text:
                segments.append(
                    {
                        "page_start": page_index + 1,
                        "page_end": page_index + 1,
                        "text": text,
                        "segment_kind": "ocr_page",
                    }
                )
    return segments


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


def extract_pdf_segments(path: Path, *, force_ocr: bool = False) -> list[dict[str, Any]]:
    import fitz

    if force_ocr:
        ocr_segments = extract_pdf_segments_with_ocr(path)
        if ocr_segments:
            return ocr_segments
        raise RuntimeError("OCR produced no text; check tesseract and installed languages")

    pymupdf_segments: list[dict[str, Any]] = []
    with fitz.open(path) as document:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text().strip()
            if text:
                pymupdf_segments.append({"page_start": page_index, "page_end": page_index, "text": text})

    pypdf_segments: list[dict[str, Any]] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        for page_index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pypdf_segments.append({"page_start": page_index, "page_end": page_index, "text": text})
    except Exception as exc:
        print(f"[documents] pypdf extraction skipped: {exc}")

    best_segments = pymupdf_segments
    best_quality = text_segments_quality(best_segments)
    pypdf_quality = text_segments_quality(pypdf_segments)
    if pypdf_segments and pypdf_quality > best_quality:
        best_segments = pypdf_segments
        best_quality = pypdf_quality

    if best_quality >= PDF_OCR_MIN_QUALITY:
        return best_segments

    print(f"[documents] PDF text quality is low ({best_quality}); trying OCR")
    ocr_segments = extract_pdf_segments_with_ocr(path)
    if ocr_segments and text_segments_quality(ocr_segments) > best_quality:
        return ocr_segments
    return best_segments


def extract_docx_segments(path: Path) -> list[dict[str, Any]]:
    from docx import Document

    document = Document(path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()).strip()
    return [{"page_start": None, "page_end": None, "text": text}] if text else []


def extract_document_segments(path: Path, suffix: str, *, force_ocr: bool = False) -> list[dict[str, Any]]:
    if suffix == ".md":
        return extract_markdown_segments(path)
    if suffix == ".txt":
        text = read_text_file(path).strip()
        return [{"page_start": None, "page_end": None, "text": text}] if text else []
    if suffix == ".pdf":
        return extract_pdf_segments(path, force_ocr=force_ocr)
    if suffix == ".docx":
        return extract_docx_segments(path)
    raise RuntimeError(f"unsupported parser for file type: {suffix}")


def normalize_document_text(text: str, *, repair_text: bool = True) -> str:
    if repair_text:
        text = repair_mojibake_text(text)
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


def process_document(document_id: int, *, force_ocr: bool = False) -> None:
    row = get_document_by_id(document_id)
    if row is None:
        raise RuntimeError("document not found for processing")

    file_path = resolve_document_path(row)
    if file_path is None or not file_path.exists():
        raise RuntimeError("uploaded file is missing")

    metadata = parse_json_field(row.get("metadata")) or {}
    suffix = Path(row["file_name"]).suffix.lower()
    source_title = clean_text_value(row.get("title")) or row["title"]
    source_type = clean_text_value(row.get("source_type"))
    segments = extract_document_segments(file_path, suffix, force_ocr=force_ocr)
    ocr_used = any(segment.get("segment_kind") == "ocr_page" for segment in segments)
    chunks = build_chunks_for_segments(
        segments,
        source_title=source_title,
        source_type=source_type,
    )
    if not chunks:
        raise RuntimeError("document text is empty after parsing")

    insert_document_chunks(document_id, chunks)
    updated_metadata = merge_document_metadata(
        metadata,
        {
            "parser": suffix.lstrip("."),
            "force_ocr": force_ocr,
            "ocr_used": ocr_used,
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


def run_retrieval(
    query: str,
    top_k: int,
    document_id: int | None = None,
) -> tuple[list[dict[str, Any]], str, int]:
    if document_id is not None:
        if document_id <= 0:
            raise HTTPException(status_code=400, detail="document_id must be a positive integer")
        document = get_document_by_id(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="document not found")
        if document.get("status") != "parsed":
            raise HTTPException(status_code=400, detail="document is not parsed yet")

    started = time.perf_counter()
    try:
        retrieve = get_retrieve()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    chunks = retrieve(query, top_k, document_id=document_id)
    latency_ms = int((time.perf_counter() - started) * 1000)
    provider = chunks[0].get("provider") if chunks else "none"
    return chunks, provider, latency_ms


def format_chunk_source_label(chunk: dict[str, Any], index: int) -> str:
    doc_label = clean_citation_text(chunk.get("doc"))
    if not doc_label and chunk.get("document_id") is not None:
        doc_label = f"Document {chunk['document_id']}"
    label = f"[Source {index + 1}] {doc_label or 'Unknown source'}"

    section_label = clean_citation_text(chunk.get("section_title"))
    if section_label and section_label not in label:
        label += f" / {section_label}"
    if chunk.get("chunk_index") is not None:
        label += f" [chunk {chunk['chunk_index']}]"
    if chunk.get("page_start") is not None and chunk.get("page_end") is not None:
        if chunk["page_start"] == chunk["page_end"]:
            label += f" (p. {chunk['page_start']})"
        else:
            label += f" (pp. {chunk['page_start']}-{chunk['page_end']})"
    return label


def build_retrieval_log_metadata(
    *,
    mode: str,
    query: str,
    top_k: int,
    provider: str,
    chunks: list[dict[str, Any]],
    retrieval_latency_ms: int,
    answer: str | None = None,
    chat_latency_ms: int | None = None,
    total_latency_ms: int | None = None,
    session_id: str | None = None,
    document_id: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    top_chunk = chunks[0] if chunks else {}
    return {
        "mode": mode,
        "prompt_mode": detect_prompt_mode(query),
        "query_length": len((query or "").strip()),
        "top_k": top_k,
        "document_id": document_id,
        "provider": provider,
        "result_count": len(chunks),
        "session_external_id": session_id,
        "retrieval_latency_ms": retrieval_latency_ms,
        "chat_latency_ms": chat_latency_ms,
        "total_latency_ms": total_latency_ms if total_latency_ms is not None else retrieval_latency_ms,
        "top_similarity": top_chunk.get("similarity"),
        "top_document_id": top_chunk.get("document_id"),
        "top_chunk_index": top_chunk.get("chunk_index"),
        "top_source": clean_citation_text(top_chunk.get("doc"), "Unknown source"),
        "top_section_title": clean_citation_text(top_chunk.get("section_title")),
        "top_embedding_model": top_chunk.get("embedding_model"),
        "answer_preview": (answer or "")[:400] if answer else None,
        "answer_length": len(answer or "") if answer is not None else None,
        "error_kind": "request_failed" if error else None,
    }


def summarize_retrieval_logs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    serialized_rows = [serialize_retrieval_log(row) for row in rows]
    total = len(serialized_rows)
    if total == 0:
        return {
            "total": 0,
            "success_count": 0,
            "failure_count": 0,
            "success_rate": None,
            "avg_retrieval_latency_ms": None,
            "avg_total_latency_ms": None,
            "slow_logs": [],
            "failed_logs": [],
            "modes": {},
            "providers": {},
        }

    success_logs = [log for log in serialized_rows if log["success"]]
    failed_logs = [log for log in serialized_rows if not log["success"]]
    retrieval_latencies = [
        log["metadata"].get("retrieval_latency_ms", log.get("latency_ms"))
        for log in serialized_rows
        if isinstance(log["metadata"].get("retrieval_latency_ms", log.get("latency_ms")), int)
    ]
    total_latencies = [
        log["metadata"].get("total_latency_ms")
        for log in serialized_rows
        if isinstance(log["metadata"].get("total_latency_ms"), int)
    ]
    mode_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    for log in serialized_rows:
        mode = log["metadata"].get("mode") or "unknown"
        provider = log.get("provider") or "unknown"
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        provider_counts[provider] = provider_counts.get(provider, 0) + 1

    def compact_log(log: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": log["id"],
            "query": log["query"],
            "provider": log.get("provider"),
            "latency_ms": log.get("latency_ms"),
            "metadata": log.get("metadata"),
            "error": log.get("error"),
            "created_at": log.get("created_at"),
        }

    slow_logs = sorted(
        serialized_rows,
        key=lambda log: log["metadata"].get("total_latency_ms", log.get("latency_ms") or 0),
        reverse=True,
    )[:5]
    return {
        "total": total,
        "success_count": len(success_logs),
        "failure_count": len(failed_logs),
        "success_rate": round(len(success_logs) / total, 4),
        "avg_retrieval_latency_ms": round(sum(retrieval_latencies) / len(retrieval_latencies), 2) if retrieval_latencies else None,
        "avg_total_latency_ms": round(sum(total_latencies) / len(total_latencies), 2) if total_latencies else None,
        "slow_logs": [compact_log(log) for log in slow_logs],
        "failed_logs": [compact_log(log) for log in failed_logs[:5]],
        "modes": mode_counts,
        "providers": provider_counts,
    }


def build_agent_evaluation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    logs = [
        serialize_retrieval_log(row)
        for row in rows
        if (parse_json_field(row.get("metadata")) or {}).get("mode") == "research_agent"
    ]
    total = len(logs)
    task_counts: dict[str, int] = {}
    no_source_questions: list[dict[str, Any]] = []
    recent_logs: list[dict[str, Any]] = []
    retrieval_latencies: list[int] = []
    successful_answers = 0

    for log in logs:
        metadata = log.get("metadata") or {}
        agent = metadata.get("agent") or {}
        citation_check = agent.get("citation_check") or {}
        task_label = agent.get("task_label") or agent.get("task") or "未识别"
        result_count = int(metadata.get("result_count") or 0)
        evidence_state = citation_check.get("evidence_state") or ("无证据" if result_count == 0 else "未检查")
        retrieval_latency = metadata.get("retrieval_latency_ms", log.get("latency_ms"))
        total_latency = metadata.get("total_latency_ms")

        task_counts[task_label] = task_counts.get(task_label, 0) + 1
        if isinstance(retrieval_latency, int):
            retrieval_latencies.append(retrieval_latency)

        has_source = result_count > 0 and evidence_state not in ("无证据", "缺少来源标注")
        if log["success"] and has_source:
            successful_answers += 1

        compact = {
            "id": log["id"],
            "query": log["query"],
            "task": agent.get("task"),
            "task_label": task_label,
            "success": log["success"],
            "result_count": result_count,
            "evidence_state": evidence_state,
            "cited_source_count": citation_check.get("cited_source_count", 0),
            "retrieval_latency_ms": retrieval_latency,
            "total_latency_ms": total_latency,
            "created_at": log["created_at"],
        }
        recent_logs.append(compact)

        if result_count == 0 or evidence_state in ("无证据", "缺少来源标注"):
            no_source_questions.append(compact)

    dominant_task = None
    if task_counts:
        dominant_task = max(task_counts.items(), key=lambda item: item[1])[0]

    return {
        "summary": {
            "total_questions": total,
            "successful_answers": successful_answers,
            "success_rate": round(successful_answers / total, 4) if total else None,
            "avg_retrieval_latency_ms": (
                round(sum(retrieval_latencies) / len(retrieval_latencies), 2)
                if retrieval_latencies
                else None
            ),
            "no_source_count": len(no_source_questions),
            "dominant_task": dominant_task,
        },
        "task_counts": task_counts,
        "no_source_questions": no_source_questions[:10],
        "recent_logs": recent_logs[:12],
    }


def detect_prompt_mode(query: str) -> str:
    text = (query or "").strip()
    if not text:
        return "default"
    if any(token in text for token in ("是否", "有没有", "有无", "明确讨论", "提到吗")):
        return "verification"
    if any(token in text for token in ("哪些", "有哪些", "主要是什么", "做了什么调整", "包括什么", "包括哪些")):
        return "listing"
    return "default"


def prompt_mode_instructions(mode: str) -> str:
    if mode == "verification":
        return (
            "Question type: verification.\n"
            "Answer with a direct conclusion first. If the sources do not explicitly state the claim, say that the sources do not explicitly say so.\n"
            "Do not infer from general architectural knowledge.\n"
        )
    if mode == "listing":
        return (
            "Question type: listing.\n"
            "Return only the concrete items explicitly supported by the sources.\n"
            "Prefer short noun phrases copied or closely paraphrased from the sources.\n"
            "Prefer concrete interventions, components, materials, or operations over abstract umbrella categories.\n"
            "If the source says 'double-glazed windows with adjustable shading blinds', keep that concrete phrase instead of replacing it with a broad label like 'shading design'.\n"
            "Do not add background explanation, examples, or generic architectural knowledge that is not stated in the sources.\n"
            "If the sources support only 2 or 3 items, return only those items instead of inventing more.\n"
            "If the sources mention several historical schemes, keep the wording tied to the scheme-specific measures instead of merging them into generic categories.\n"
            "If a candidate item is only loosely implied, leave it out.\n"
        )
    return (
        "Question type: general.\n"
        "Answer narrowly and stay close to the wording of the sources.\n"
        "Do not add outside knowledge or broaden the scope beyond what the sources support.\n"
    )


def build_prompt(query: str, chunks: list[dict[str, Any]]) -> str:
    prompt_mode = detect_prompt_mode(query)
    context = "\n\n".join(
        f"{format_chunk_source_label(chunk, index)}\n{chunk.get('content', '')}"
        for index, chunk in enumerate(chunks)
    )
    return f"""You are ZhiYu, an academic assistant for architectural heritage research.
Answer only from the provided sources. If the sources do not contain enough
information, say so clearly. Do not use outside knowledge. Do not generalize
beyond what is explicitly supported by the sources.

{prompt_mode_instructions(prompt_mode)}

Follow these rules:
1. Use only information that appears in the sources below.
2. Prefer concrete phrases from the sources over abstract summaries.
3. Do not add extra examples, standard practices, or background facts unless the sources explicitly mention them.
4. If multiple periods or schemes are mentioned, keep them distinct instead of merging them loosely.
5. Keep the answer concise and evidence-bound.
6. For listing questions, output only the supported items. Do not pad the list.
7. End with a short `Sources:` line that lists the source labels you used, for example `Sources: [Source 1], [Source 3]`.

Sources:
{context}

User question:
{query}
"""


AGENT_TASK_LABELS = {
    "literature_summary": "文献摘要",
    "multi_document_comparison": "多文献对比",
    "related_research_search": "全库检索",
    "cited_literature_review": "带引用综述",
}


def detect_research_agent_task(query: str, document_id: int | None = None) -> str:
    text = (query or "").strip().lower()
    if any(token in text for token in ("对比", "比较", "差异", "异同", "compare", "comparison")):
        return "multi_document_comparison"
    if any(token in text for token in ("综述", "研究现状", "文献回顾", "写一段", "review", "synthesis")):
        return "cited_literature_review"
    if any(token in text for token in ("相关研究", "找研究", "找文献", "推荐文献", "有哪些研究", "search")):
        return "related_research_search"
    if document_id is not None or any(
        token in text
        for token in ("这篇", "本文", "讲什么", "讲了什么", "主要讲", "主要内容", "核心观点", "摘要", "总结", "summarize")
    ):
        return "literature_summary"
    return "related_research_search"


def list_parsed_documents_for_agent(limit: int = 80) -> list[dict[str, Any]]:
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
        WHERE d.status = 'parsed'
        GROUP BY d.id
        ORDER BY d.created_at DESC, d.id DESC
        LIMIT {mark}
        """,
        (limit,),
    )
    return [serialize_document(row) for row in fetch_all_dicts(cursor)]


def extract_requested_document_ids(query: str, documents: list[dict[str, Any]]) -> list[int]:
    known_ids = {int(document["id"]) for document in documents}
    ids: list[int] = []
    patterns = (
        r"(?:doc(?:ument)?|文献|文件|资料)\s*#?\s*(\d+)",
        r"#(\d+)",
    )
    for pattern in patterns:
        for match in re.findall(pattern, query or "", flags=re.IGNORECASE):
            document_id = int(match)
            if document_id in known_ids and document_id not in ids:
                ids.append(document_id)

    normalized_query = normalize_document_match_text(query)
    for document in documents:
        document_id = int(document["id"])
        if document_id in ids:
            continue

        candidates = [
            document.get("title"),
            document.get("file_name"),
            (document.get("metadata") or {}).get("original_file_name")
            if isinstance(document.get("metadata"), dict)
            else None,
        ]
        for candidate in candidates:
            normalized_candidate = normalize_document_match_text(str(candidate or ""))
            if not normalized_candidate or len(normalized_candidate) < 6:
                continue
            if normalized_candidate in normalized_query:
                ids.append(document_id)
                break
    return ids


def normalize_document_match_text(value: str | None) -> str:
    text = repair_mojibake_text(value).lower()
    text = re.sub(r"\.(pdf|docx|doc|txt|md)$", "", text, flags=re.IGNORECASE)
    return re.sub(r"[\s\-_《》<>〈〉「」『』“”\"'.,，。:：;；/\\()\[\]（）【】]+", "", text)


def representative_document_chunks(document_id: int, *, limit: int = 6) -> list[dict[str, Any]]:
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    if row.get("status") != "parsed":
        raise HTTPException(status_code=400, detail="document is not parsed yet")

    title = clean_citation_text(row.get("title"), row.get("file_name")) or f"Document {document_id}"
    chunks = []
    for index, chunk in enumerate(list_document_chunks(document_id, limit=limit)):
        page_suffix = ""
        if chunk.get("page_start") is not None and chunk.get("page_end") is not None:
            if chunk["page_start"] == chunk["page_end"]:
                page_suffix = f" (p. {chunk['page_start']})"
            else:
                page_suffix = f" (pp. {chunk['page_start']}-{chunk['page_end']})"
        section_suffix = f" / {chunk['section_title']}" if chunk.get("section_title") else ""
        chunks.append(
            {
                "content": chunk.get("content", ""),
                "doc": f"{title}{section_suffix}{page_suffix}",
                "similarity": max(0.2, 1.0 - index * 0.08),
                "document_id": document_id,
                "provider": "document_chunks",
                "source_type": row.get("source_type"),
                "section_title": chunk.get("section_title"),
                "chunk_index": chunk.get("chunk_index"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
            }
        )
    return chunks


RESEARCH_CARD_FIELDS = [
    ("research_object", "研究对象"),
    ("core_question", "核心问题"),
    ("main_arguments", "主要观点"),
    ("method_or_material", "方法 / 材料 / 案例"),
    ("key_findings", "关键结论"),
    ("theoretical_contribution", "理论贡献"),
    ("research_value", "对研究的启发"),
    ("limitations", "局限或待确认处"),
    ("suggested_category", "建议分类"),
    ("suggested_tags", "建议标签"),
    ("suggested_keywords", "建议关键词"),
]


def normalize_card_value(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value).strip()


def split_metadata_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[,，;；、\n]", str(value))

    items = []
    for raw_item in raw_items:
        item = clean_text_value(str(raw_item))
        if item and item not in items:
            items.append(item)
    return items


def merge_metadata_items(existing: Any, suggested: Any) -> list[str]:
    items = split_metadata_items(existing)
    for item in split_metadata_items(suggested):
        if item not in items:
            items.append(item)
    return items


def research_card_metadata_updates(metadata: dict[str, Any], card: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {"research_card": card}
    suggested_category = clean_text_value(
        normalize_card_value(card.get("suggested_category") or card.get("category"))
    )
    if suggested_category and not clean_text_value(str(metadata.get("category") or "")):
        updates["category"] = suggested_category

    merged_tags = merge_metadata_items(metadata.get("tags"), card.get("suggested_tags") or card.get("tags"))
    if merged_tags:
        updates["tags"] = merged_tags

    merged_keywords = merge_metadata_items(
        metadata.get("keywords"),
        card.get("suggested_keywords") or card.get("keywords"),
    )
    if merged_keywords:
        updates["keywords"] = merged_keywords

    return updates


def parse_research_card_json(raw_text: str) -> dict[str, str] | None:
    text = (raw_text or "").strip()
    if not text:
        return None

    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return {
                key: normalize_card_value(parsed.get(key))
                for key, _label in RESEARCH_CARD_FIELDS
            }
    return None


def format_research_card(card: dict[str, Any]) -> str:
    lines = []
    for key, label in RESEARCH_CARD_FIELDS:
        value = normalize_card_value(card.get(key))
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines)


def fallback_research_card(row: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, str]:
    title = clean_citation_text(row.get("title"), row.get("file_name")) or f"Document {row.get('id')}"
    excerpts = [
        repair_mojibake_text(chunk.get("content", "")).strip().replace("\n", " ")
        for chunk in chunks[:5]
        if chunk.get("content")
    ]
    evidence = "；".join(excerpt[:180] for excerpt in excerpts if excerpt)
    keyword_candidates = []
    for value in [title, row.get("author"), row.get("source_type"), evidence[:300]]:
        for item in re.split(r"[_\s,，;；、：《》“”\"'（）()]+", str(value or "")):
            item = clean_text_value(item)
            if item and 2 <= len(item) <= 12 and item not in keyword_candidates:
                keyword_candidates.append(item)
    return {
        "research_object": title,
        "core_question": "需要结合全文进一步确认；当前可从代表片段中初步判断。",
        "main_arguments": evidence or "当前片段不足以稳定提炼主要观点。",
        "method_or_material": "需要结合正文、案例或材料段落进一步确认。",
        "key_findings": evidence or "当前片段不足以稳定提炼关键结论。",
        "theoretical_contribution": "需要结合引言、结论和理论讨论段落进一步确认。",
        "research_value": "可作为后续精读和提问的初步索引。",
        "limitations": "这是基于已解析片段生成的初步卡片，不等同于全文人工精读。",
        "suggested_category": clean_text_value(row.get("source_type")) or "未分类",
        "suggested_tags": "；".join(keyword_candidates[:5]),
        "suggested_keywords": "；".join(keyword_candidates[:8]),
    }


def build_research_card_prompt(row: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
    title = clean_citation_text(row.get("title"), row.get("file_name")) or f"Document {row.get('id')}"
    context = "\n\n".join(
        f"[Fragment {index}]\n{chunk.get('content', '')}"
        for index, chunk in enumerate(chunks[:12], start=1)
    )
    keys = ", ".join(key for key, _label in RESEARCH_CARD_FIELDS)
    return f"""You are ZhiYu, an academic literature assistant.
Create a structured research card for one paper. Use only the fragments below.
Return valid JSON only, with these keys: {keys}.
Use concise Chinese. If a field is not clearly supported, write "文献片段中暂不明确".
For suggested_category, give one short category. For suggested_tags and suggested_keywords, return 3-8 concise items.

Paper title:
{title}

Fragments:
{context}
"""


def get_document_research_card(row: dict[str, Any]) -> dict[str, Any] | None:
    metadata = parse_json_field(row.get("metadata")) or {}
    card = metadata.get("research_card")
    return card if isinstance(card, dict) else None


def build_document_research_card(document_id: int, *, force: bool = False) -> dict[str, Any]:
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")
    if row.get("status") != "parsed":
        raise HTTPException(status_code=400, detail="document is not parsed yet")

    existing = get_document_research_card(row)
    if existing and not force:
        return existing

    chunks = list_document_chunks(document_id, limit=12)
    if not chunks:
        raise HTTPException(status_code=400, detail="document has no parsed chunks")

    card = None
    if HUNYUAN_API_KEY.strip():
        raw_card = chat_with_hunyuan(build_research_card_prompt(row, chunks))
        if not raw_card.startswith("LLM call failed") and not raw_card.startswith("LLM is not configured"):
            card = parse_research_card_json(raw_card)

    if not card:
        card = fallback_research_card(row, chunks)

    card = {
        **card,
        "document_id": document_id,
        "document_title": clean_citation_text(row.get("title"), row.get("file_name")) or row.get("file_name"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": "research_card_v1",
    }
    metadata = parse_json_field(row.get("metadata")) or {}
    update_document_record(
        document_id,
        metadata=merge_document_metadata(metadata, research_card_metadata_updates(metadata, card)),
    )
    return card


def try_build_document_research_card(document_id: int, *, force: bool = False) -> dict[str, Any] | None:
    try:
        return build_document_research_card(document_id, force=force)
    except Exception as exc:
        row = get_document_by_id(document_id)
        metadata = parse_json_field(row.get("metadata")) if row else {}
        update_document_record(
            document_id,
            metadata=merge_document_metadata(
                metadata or {},
                {
                    "research_card_error": str(exc),
                    "research_card_error_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
            ),
        )
        print(f"[research-card] generation failed document_id={document_id}: {exc}")
        return None


def research_card_to_chunk(document_id: int, card: dict[str, Any]) -> dict[str, Any]:
    title = normalize_card_value(card.get("document_title")) or f"Document {document_id}"
    return {
        "content": format_research_card(card),
        "doc": f"{title} / 文献卡片",
        "similarity": 1.0,
        "document_id": document_id,
        "provider": "research_card",
        "source_type": "research_card",
        "section_title": "文献卡片",
        "chunk_index": None,
        "page_start": None,
        "page_end": None,
    }


def document_summary_for_agent(document: dict[str, Any]) -> str:
    title = document.get("title") or document.get("file_name") or f"Document {document.get('id')}"
    details = [f"#{document.get('id')} {title}"]
    if document.get("author"):
        details.append(str(document["author"]))
    if document.get("year"):
        details.append(str(document["year"]))
    if document.get("chunk_count") is not None:
        details.append(f"{document['chunk_count']} chunks")
    return " / ".join(details)


def source_selection_reason(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "没有找到可用来源。"
    document_ids = sorted({chunk.get("document_id") for chunk in chunks if chunk.get("document_id") is not None})
    if document_ids:
        return f"优先选择得分靠前、能覆盖问题关键词的片段，涉及文献 ID：{', '.join(map(str, document_ids))}。"
    return "优先选择得分靠前、内容与问题最接近的片段。"


def citation_audit(answer: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    available_labels = [f"[Source {index}]" for index in range(1, len(chunks) + 1)]
    cited_labels = [label for label in available_labels if label in (answer or "")]
    unsupported_labels = sorted(set(re.findall(r"\[Source\s+\d+\]", answer or "")) - set(available_labels))
    if not chunks:
        evidence_state = "无证据"
    elif cited_labels and not unsupported_labels:
        evidence_state = "已标注来源"
    elif cited_labels:
        evidence_state = "部分来源异常"
    else:
        evidence_state = "缺少来源标注"

    return {
        "evidence_state": evidence_state,
        "available_source_count": len(available_labels),
        "cited_source_count": len(cited_labels),
        "cited_sources": cited_labels,
        "unsupported_citations": unsupported_labels,
    }


def build_research_agent_prompt(
    *,
    query: str,
    task: str,
    chunks: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    steps: list[dict[str, Any]],
) -> str:
    context = "\n\n".join(
        f"{format_chunk_source_label(chunk, index)}\n{chunk.get('content', '')}"
        for index, chunk in enumerate(chunks)
    )
    document_context = "\n".join(document_summary_for_agent(document) for document in documents[:20])
    task_label = AGENT_TASK_LABELS.get(task, task)
    if task == "multi_document_comparison":
        output_rule = "Output a concise comparison table first, then 2-4 bullet points explaining the main similarities and differences."
    elif task == "cited_literature_review":
        output_rule = "Write one short literature-review paragraph, then list the supporting claims. Every claim must cite source labels."
    elif task == "literature_summary":
        output_rule = "Summarize the paper in four parts: research question, method/material, key findings, and value for architectural research."
    else:
        output_rule = "List the most relevant studies or source passages, grouped by theme when possible."

    trace = "\n".join(f"- {step['name']}: {step['detail']}" for step in steps)
    return f"""You are ZhiYu Research Agent, an architecture literature research assistant.
The current task is: {task_label}.

Evidence rules:
1. Use only the provided sources. Do not use outside knowledge.
2. Every factual conclusion must end with one or more source labels, such as [Source 1] or [Source 1][Source 3].
3. Do not cite a source unless that source directly supports the sentence.
4. If the sources do not directly support a claim, write: "文献库中暂时没有直接证据说明……"
5. Do not invent paper titles, authors, years, page numbers, methods, data, or conclusions.
6. End with one short line: "证据状态：充分 / 部分 / 不足"，choose based only on the provided sources.

Keep the answer useful for an architecture graduate student preparing research notes.
{output_rule}

Available parsed documents:
{document_context or "No parsed documents."}

Agent workflow:
{trace}

Sources:
{context or "No sources were found."}

User request:
{query}
"""


def fallback_research_agent_answer(task: str, chunks: list[dict[str, Any]], query: str) -> str:
    if not chunks:
        return "信息不足：文献库中暂时没有查到能直接支持回答的内容。可以先上传或解析更多相关文献，再重新提问。\n\n证据状态：不足"

    source_lines = []
    for index, chunk in enumerate(chunks[:5], start=1):
        title = clean_citation_text(chunk.get("doc"), f"Source {index}") or f"Source {index}"
        excerpt = repair_mojibake_text(chunk.get("content", "")).strip().replace("\n", " ")
        source_lines.append(f"[Source {index}] {title}: {excerpt[:180]}")

    if task == "multi_document_comparison":
        rows = "\n".join(
            f"| [Source {index}] | {clean_citation_text(chunk.get('doc'), 'Unknown source') or 'Unknown source'} | {repair_mojibake_text(chunk.get('content', '')).strip().replace(chr(10), ' ')[:120]} |"
            for index, chunk in enumerate(chunks[:5], start=1)
        )
        return f"我先按已找到的来源做一个粗略对比：\n\n| 来源 | 文献 | 相关内容 |\n| --- | --- | --- |\n{rows}\n\n当前没有配置大模型时，我只能基于片段摘出差异点；配置模型后会自动生成更完整的对比结论。\n\n证据状态：部分"

    if task == "cited_literature_review":
        return (
            f"围绕“{query}”，目前可先形成一个初步综述：已有片段显示，相关讨论主要集中在下列来源中，"
            "后续可继续扩大检索范围并补充更完整的主题归纳。\n\n"
            + "\n".join(f"- {line}" for line in source_lines)
            + "\n\n证据状态：部分"
        )

    if task == "literature_summary":
        return (
            "这篇文献的初步摘要如下：\n"
            "1. 研究对象和问题可从前几个片段中提取。\n"
            "2. 方法、材料和案例需要结合全文片段继续确认。\n"
            "3. 当前最可靠的依据如下：\n"
            + "\n".join(f"- {line}" for line in source_lines[:4])
            + "\n\n证据状态：部分"
        )

    return "我找到的相关研究如下：\n\n" + "\n".join(f"- {line}" for line in source_lines) + "\n\n证据状态：部分"


def append_source_labels(answer: str, chunks: list[dict[str, Any]]) -> str:
    labels = [f"[Source {index}]" for index in range(1, min(len(chunks), 5) + 1)]
    if not labels:
        return answer

    cleaned_answer = (answer or "").strip()
    source_line = "Sources: " + ", ".join(labels)
    evidence_line = "证据状态：部分"

    if not cleaned_answer:
        return f"{source_line}\n{evidence_line}"
    if "Sources:" in cleaned_answer or "来源：" in cleaned_answer:
        return cleaned_answer
    if "证据状态：" in cleaned_answer:
        return f"{cleaned_answer}\n{source_line}"
    return f"{cleaned_answer}\n\n{source_line}\n{evidence_line}"


def enforce_cited_answer(answer: str, task: str, chunks: list[dict[str, Any]], query: str) -> tuple[str, dict[str, Any]]:
    audit = citation_audit(answer, chunks)
    if not chunks:
        insufficient_answer = fallback_research_agent_answer(task, chunks, query)
        return insufficient_answer, citation_audit(insufficient_answer, chunks)

    if audit["cited_source_count"] > 0 and not audit["unsupported_citations"]:
        return answer, audit

    if not answer.strip() or "LLM is not configured" in answer:
        fallback_answer = fallback_research_agent_answer(task, chunks, query)
        return fallback_answer, citation_audit(fallback_answer, chunks)

    cited_answer = append_source_labels(answer, chunks)
    return cited_answer, citation_audit(cited_answer, chunks)


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
    conversation_sources = sources if sources else "[]"
    db_conn.execute(
        "INSERT INTO conversations (session_id, role, content, sources) "
        f"VALUES ({mark}, {mark}, {mark}, {mark})",
        (session_id, role, content, conversation_sources),
    )
    structured_session_id = ensure_default_session(db_conn, session_id)
    insert_message(db_conn, structured_session_id, role, content, conversation_sources, metadata="{}")
    db_conn.commit()


def ensure_structured_session_id(session_id: str | None) -> int | None:
    if not session_id:
        return None
    return ensure_default_session(db_conn, session_id)


def find_structured_session_id(session_id: str | None) -> int | None:
    if not session_id or not using_postgres():
        return None

    cursor = db_conn.execute(
        "SELECT id FROM sessions WHERE metadata->>'external_session_id' = %s LIMIT 1",
        (session_id,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


@app.get("/api/ocr/status")
def get_ocr_status():
    tesseract_path = shutil.which("tesseract")
    status: dict[str, Any] = {
        "tesseract_path": tesseract_path,
        "tesseract_version": None,
        "cli_languages": [],
        "pytesseract_languages": [],
        "has_chi_sim": False,
        "errors": [],
    }

    if not tesseract_path:
        status["errors"].append("tesseract command was not found on PATH")
        return status

    try:
        version = subprocess.run(
            ["tesseract", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status["tesseract_version"] = (version.stdout or version.stderr).splitlines()[0]
    except Exception as exc:
        status["errors"].append(f"failed to read tesseract version: {exc}")

    try:
        langs = subprocess.run(
            ["tesseract", "--list-langs"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status["cli_languages"] = [
            line.strip()
            for line in (langs.stdout or "").splitlines()
            if line.strip() and not line.lower().startswith("list of available")
        ]
    except Exception as exc:
        status["errors"].append(f"failed to list tesseract languages: {exc}")

    try:
        import pytesseract

        status["pytesseract_languages"] = pytesseract.get_languages(config="")
    except Exception as exc:
        status["errors"].append(f"failed to list pytesseract languages: {exc}")

    all_languages = set(status["cli_languages"]) | set(status["pytesseract_languages"])
    status["has_chi_sim"] = "chi_sim" in all_languages
    return status


@app.get("/api/storage/status")
def get_storage_status():
    missing = supabase_storage_missing_config()
    url_looks_like_project_root = SUPABASE_URL.startswith("https://") and SUPABASE_URL.endswith(".supabase.co")
    return {
        "use_supabase_storage": USE_SUPABASE_STORAGE,
        "configured": supabase_storage_configured(),
        "missing": missing,
        "supabase_url_set": bool(SUPABASE_URL),
        "supabase_url_looks_like_project_root": url_looks_like_project_root,
        "service_role_key_set": bool(SUPABASE_SERVICE_ROLE_KEY),
        "service_role_key_looks_secret": SUPABASE_SERVICE_ROLE_KEY.startswith("sb_secret_"),
        "bucket": SUPABASE_STORAGE_BUCKET,
        "prefix": SUPABASE_STORAGE_PREFIX,
        "public": SUPABASE_STORAGE_PUBLIC,
    }


@app.post("/api/storage/test")
def test_storage_write():
    require_supabase_storage_if_enabled()
    try:
        return test_supabase_storage_write()
    except Exception as exc:
        print(f"[storage] healthcheck failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/embeddings/status")
def get_embeddings_status():
    status = embedding_status()
    status.update(embedding_counts())
    return status


@app.post("/api/embeddings/test")
def test_embeddings():
    try:
        vector = embed_texts(["测试文本"])[0]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"embedding test failed: {exc}") from exc

    return {
        "ok": True,
        "model": EMBEDDING_MODEL,
        "dimension": len(vector),
        "sample": vector[:5],
    }


@app.post("/api/documents/{document_id}/embeddings")
def create_document_embeddings(document_id: int, force: bool = False):
    try:
        result = build_document_embeddings(document_id, force=force)
        db_conn.commit()
    except Exception as exc:
        db_conn.rollback()
        raise HTTPException(status_code=500, detail=f"embedding build failed: {exc}") from exc
    return result


@app.post("/api/documents/upload")
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    year: str | None = Form(None),
    source_type: str | None = Form(None),
    metadata: str | None = Form(None),
    force_ocr: bool = Form(False),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="file name is required")

    original_name = Path(file.filename).name
    display_name = Path(repair_mojibake_text(original_name)).name or original_name
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
    document_title = repair_mojibake_text(title or Path(display_name).stem).strip()
    if not document_title:
        raise HTTPException(status_code=400, detail="title is required")
    document_author = clean_text_value(author)
    document_source_type = clean_text_value(source_type)
    storage_info: dict[str, str] | None = None

    require_supabase_storage_if_enabled()

    try:
        with storage_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)
    finally:
        file.file.close()

    if supabase_storage_configured():
        try:
            storage_info = upload_file_to_supabase_storage(
                file_path=storage_path,
                storage_name=storage_name,
                content_type=file.content_type,
            )
        except Exception as exc:
            if storage_path.exists():
                storage_path.unlink()
            raise HTTPException(status_code=500, detail=f"Supabase Storage upload failed: {exc}") from exc

    metadata_payload.update(
        {
            "content_type": file.content_type,
            "storage_name": storage_name,
            "original_file_name": display_name,
        }
    )
    if storage_info:
        metadata_payload.update(
            {
                "storage_provider": storage_info["provider"],
                "storage_bucket": storage_info["bucket"],
                "storage_path": storage_info["path"],
                "storage_url": storage_info["url"],
                "storage_public_url": storage_info["public_url"] if SUPABASE_STORAGE_PUBLIC else None,
            }
        )

    try:
        document_id = insert_document_record(
            title=document_title,
            author=document_author,
            year=(year or "").strip() or None,
            source_type=document_source_type,
            file_name=display_name,
            file_type=suffix.lstrip(".").upper(),
            file_size=storage_path.stat().st_size,
            status="processing",
            metadata=metadata_payload,
        )
        file_url = (
            storage_info["public_url"]
            if storage_info and SUPABASE_STORAGE_PUBLIC
            else f"/api/documents/{document_id}/file"
        )
        update_document_file_url(document_id, file_url)
        if not storage_info:
            store_document_file_blob(
                document_id,
                file_name=display_name,
                content_type=file.content_type,
                file_path=storage_path,
            )
        db_conn.commit()
    except Exception:
        db_conn.rollback()
        if storage_info:
            delete_supabase_storage_file(storage_info["path"])
        if storage_path.exists():
            storage_path.unlink()
        raise

    try:
        process_document(document_id, force_ocr=force_ocr)
        try_build_document_embeddings(document_id, force=True)
        try_build_document_research_card(document_id)
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
                    "force_ocr": force_ocr,
                },
            ),
        )
        db_conn.commit()

    row = get_document_by_id(document_id)
    if storage_info and storage_path.exists():
        storage_path.unlink()
    if row is None:
        raise HTTPException(status_code=500, detail="document record was not created")
    return {"document": serialize_document(row)}


@app.post("/api/documents/text")
def create_text_document(req: TextDocumentRequest):
    title = clean_text_value(req.title)
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    content = normalize_document_text(req.content, repair_text=False)
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    source_type = clean_text_value(req.source_type) or "text_input"
    metadata_payload = merge_document_metadata(
        req.metadata or {},
        {
            "parser": "text_input",
            "input_method": "direct_text",
            "parse_error": None,
        },
    )

    try:
        document_id = insert_document_record(
            title=title,
            author=clean_text_value(req.author),
            year=(req.year or "").strip() or None,
            source_type=source_type,
            file_name=f"{title}.txt",
            file_type="TEXT",
            file_size=len(content.encode("utf-8")),
            status="processing",
            metadata=metadata_payload,
        )
        chunks = build_chunks_for_segments(
            [
                {
                    "page_start": None,
                    "page_end": None,
                    "text": content,
                    "section_title": title,
                    "segment_kind": "direct_text",
                }
            ],
            source_title=title,
            source_type=source_type,
        )
        if not chunks:
            raise RuntimeError("text produced no chunks")
        insert_document_chunks(document_id, chunks, repair_text=False)
        update_document_record(
            document_id,
            status="parsed",
            metadata=merge_document_metadata(
                metadata_payload,
                {
                    "segment_count": 1,
                    "chunk_count": len(chunks),
                },
            ),
        )
        try_build_document_embeddings(document_id, force=True)
        try_build_document_research_card(document_id)
        db_conn.commit()
    except Exception as exc:
        db_conn.rollback()
        raise HTTPException(status_code=500, detail=f"text document creation failed: {exc}") from exc

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


@app.patch("/api/documents/{document_id}/metadata")
def update_document_metadata(document_id: int, req: DocumentMetadataUpdate):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    def clean_items(values: list[str] | None) -> list[str]:
        if not values:
            return []
        cleaned = []
        for value in values:
            item = clean_text_value(value)
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned

    metadata = parse_json_field(row.get("metadata")) or {}
    updated_metadata = merge_document_metadata(
        metadata,
        {
            "category": clean_text_value(req.category),
            "tags": clean_items(req.tags),
            "keywords": clean_items(req.keywords),
        },
    )
    update_document_record(document_id, metadata=updated_metadata)
    db_conn.commit()

    updated = get_document_by_id(document_id)
    return {"document": serialize_document(updated) if updated else None}


@app.get("/api/documents/{document_id}/storage-status")
def get_document_storage_status(document_id: int):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    metadata = parse_json_field(row.get("metadata")) or {}
    storage_name = metadata.get("storage_name")
    file_path = None
    local_exists = False
    local_size = None
    if storage_name:
        candidate_path = (UPLOAD_DIR / storage_name).resolve()
        upload_root = UPLOAD_DIR.resolve()
        if upload_root in candidate_path.parents or candidate_path == upload_root:
            file_path = str(candidate_path)
            local_exists = candidate_path.exists()
            local_size = candidate_path.stat().st_size if local_exists else None

    mark = placeholder()
    cursor = db_conn.cursor()
    cursor.execute(
        f"SELECT file_name, content_type, file_size, data IS NOT NULL AS has_data FROM document_files WHERE document_id = {mark}",
        (document_id,),
    )
    blob_row = fetch_one_dict(cursor)
    return {
        "document_id": document_id,
        "storage_name": storage_name,
        "local_path": file_path,
        "local_exists": local_exists,
        "local_size": local_size,
        "storage_provider": metadata.get("storage_provider"),
        "storage_bucket": metadata.get("storage_bucket"),
        "storage_path": metadata.get("storage_path"),
        "storage_url": metadata.get("storage_url"),
        "database_file": blob_row,
    }


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


@app.post("/api/documents/{document_id}/research-card")
def create_document_research_card(document_id: int, force: bool = False):
    try:
        card = build_document_research_card(document_id, force=force)
        db_conn.commit()
    except HTTPException:
        db_conn.rollback()
        raise
    except Exception as exc:
        db_conn.rollback()
        raise HTTPException(status_code=500, detail=f"research card generation failed: {exc}") from exc

    row = get_document_by_id(document_id)
    return {
        "document": serialize_document(row) if row else None,
        "research_card": card,
    }


@app.get("/api/documents/{document_id}/research-card")
def api_get_document_research_card(document_id: int):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    card = get_document_research_card(row)
    if card is None:
        raise HTTPException(status_code=404, detail="research card has not been generated")

    return {
        "document": serialize_document(row),
        "research_card": card,
    }


@app.post("/api/documents/{document_id}/ocr-preview")
def preview_document_ocr(document_id: int, pages: int = 2):
    if pages < 1 or pages > 5:
        raise HTTPException(status_code=400, detail="pages must be between 1 and 5")

    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    file_path = resolve_document_path(row)
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="uploaded file is missing")

    suffix = Path(row["file_name"]).suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="OCR preview is only available for PDF documents")

    segments = extract_pdf_segments_with_ocr(file_path, max_pages=pages)
    return {
        "document_id": document_id,
        "pages": pages,
        "segments": [
            {
                "page_start": segment.get("page_start"),
                "page_end": segment.get("page_end"),
                "text": normalize_document_text(segment.get("text", "")),
                "quality": text_segments_quality([segment]),
            }
            for segment in segments
        ],
        "segment_count": len(segments),
    }


@app.post("/api/documents/{document_id}/reprocess")
def reprocess_document(document_id: int, force_ocr: bool = False):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    file_path = resolve_document_path(row)
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="uploaded file is missing")

    try:
        update_document_text_fields(
            document_id,
            title=clean_text_value(row.get("title")),
            author=clean_text_value(row.get("author")),
            source_type=clean_text_value(row.get("source_type")),
        )
        update_document_record(document_id, status="processing")
        process_document(document_id, force_ocr=force_ocr)
        try_build_document_embeddings(document_id, force=True)
        try_build_document_research_card(document_id, force=True)
        db_conn.commit()
    except Exception as exc:
        db_conn.rollback()
        failure_row = get_document_by_id(document_id)
        failure_metadata = parse_json_field(failure_row.get("metadata")) if failure_row else {}
        update_document_record(
            document_id,
            status="failed",
            metadata=merge_document_metadata(
                failure_metadata or {},
                {
                    "parse_error": str(exc),
                    "chunk_count": 0,
                    "force_ocr": force_ocr,
                },
            ),
        )
        db_conn.commit()
        raise HTTPException(status_code=500, detail=f"document reprocess failed: {exc}") from exc

    updated = get_document_by_id(document_id)
    if updated is None:
        raise HTTPException(status_code=500, detail="document record disappeared after reprocess")
    return {"document": serialize_document(updated)}


@app.get("/api/documents/{document_id}/file")
def get_document_file(document_id: int):
    row = get_document_by_id(document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="document not found")

    metadata = parse_json_field(row.get("metadata")) or {}
    if metadata.get("storage_provider") == "supabase_storage" and metadata.get("storage_path"):
        try:
            data = download_supabase_storage_file(str(metadata["storage_path"]))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="file not found in Supabase Storage") from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Supabase Storage download failed: {exc}") from exc

        file_name = repair_mojibake_text(row.get("file_name")) or f"document-{document_id}"
        content_type = metadata.get("content_type") or mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        headers = {
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(file_name)}",
        }
        return Response(content=data, media_type=content_type, headers=headers)

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
    try:
        chunks, provider, latency_ms = run_retrieval(req.query, req.top_k, req.document_id)
        formatted_chunks = format_chunks(chunks)
        log_metadata = build_retrieval_log_metadata(
            mode="retrieve",
            query=req.query,
            top_k=req.top_k,
            provider=provider,
            chunks=formatted_chunks,
            retrieval_latency_ms=latency_ms,
            document_id=req.document_id,
        )
        insert_retrieval_log(
            session_id=None,
            query=req.query,
            provider=provider,
            top_k=req.top_k,
            results=formatted_chunks,
            latency_ms=latency_ms,
            success=True,
            metadata=log_metadata,
        )
        db_conn.commit()
        return {"chunks": formatted_chunks}
    except HTTPException as exc:
        log_metadata = build_retrieval_log_metadata(
            mode="retrieve",
            query=req.query,
            top_k=req.top_k,
            provider="unavailable",
            chunks=[],
            retrieval_latency_ms=0,
            document_id=req.document_id,
            error=str(exc.detail),
        )
        insert_retrieval_log(
            session_id=None,
            query=req.query,
            provider="unavailable",
            top_k=req.top_k,
            results=[],
            latency_ms=0,
            success=False,
            error=str(exc.detail),
            metadata=log_metadata,
        )
        db_conn.commit()
        raise


@app.post("/api/agent/research")
def api_research_agent(req: ResearchAgentRequest):
    session_id = req.session_id or "default"
    structured_session_id = ensure_structured_session_id(session_id)
    request_started = time.perf_counter()
    retrieval_started = time.perf_counter()
    provider = "research_agent"
    raw_chunks: list[dict[str, Any]] = []
    formatted_chunks: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []

    try:
        documents = list_parsed_documents_for_agent()
        task = detect_research_agent_task(req.query, req.document_id)
        task_label = AGENT_TASK_LABELS.get(task, task)
        steps.append(
            {
                "name": "任务识别",
                "tool": "detect_task",
                "detail": f"识别为「{task_label}」。",
                "status": "done",
            }
        )
        steps.append(
            {
                "name": "读取文献列表",
                "tool": "list_documents",
                "detail": f"找到 {len(documents)} 篇已解析文献。",
                "status": "done",
            }
        )

        requested_ids = extract_requested_document_ids(req.query, documents)
        if req.document_id is not None and req.document_id not in requested_ids:
            requested_ids.insert(0, req.document_id)

        retrieval_top_k = max(3, min(max(req.top_k, 8), 20))
        if task == "literature_summary" and requested_ids:
            for document_id in requested_ids[:1]:
                card = build_document_research_card(document_id)
                raw_chunks.append(research_card_to_chunk(document_id, card))
                raw_chunks.extend(representative_document_chunks(document_id, limit=max(3, retrieval_top_k - 1)))
            provider = "document_chunks"
            steps.append(
                {
                    "name": "查看文献片段",
                    "tool": "view_chunks",
                    "detail": f"读取文献 {requested_ids[0]} 的代表片段，用于生成摘要。",
                    "status": "done",
                }
            )
        elif task == "multi_document_comparison" and len(requested_ids) >= 2:
            for document_id in requested_ids[:4]:
                raw_chunks.extend(representative_document_chunks(document_id, limit=3))
            provider = "document_chunks"
            steps.append(
                {
                    "name": "查看多篇文献片段",
                    "tool": "view_chunks",
                    "detail": f"读取 {len(requested_ids[:4])} 篇指定文献的代表片段，用于生成对比表。",
                    "status": "done",
                }
            )
        else:
            search_document_id = req.document_id if task == "literature_summary" else None
            raw_chunks, provider, _ = run_retrieval(req.query, retrieval_top_k, search_document_id)
            steps.append(
                {
                    "name": "检索文献",
                    "tool": "full_library_search" if search_document_id is None else "document_search",
                    "detail": (
                        f"在全库中检索，返回 {len(raw_chunks)} 个候选片段。"
                        if search_document_id is None
                        else f"在文献 {search_document_id} 内检索，返回 {len(raw_chunks)} 个候选片段。"
                    ),
                    "status": "done",
                }
            )

        retrieval_latency_ms = int((time.perf_counter() - retrieval_started) * 1000)
        formatted_chunks = format_chunks(raw_chunks)
        steps.append(
            {
                "name": "筛选来源",
                "tool": "select_sources",
                "detail": source_selection_reason(formatted_chunks),
                "status": "done",
            }
        )

        prompt = build_research_agent_prompt(
            query=req.query,
            task=task,
            chunks=raw_chunks,
            documents=documents,
            steps=steps,
        )
        llm_started = time.perf_counter()
        if HUNYUAN_API_KEY.strip() and raw_chunks:
            answer = chat_with_hunyuan(prompt)
        else:
            answer = fallback_research_agent_answer(task, formatted_chunks, req.query)
        answer, citation_check = enforce_cited_answer(answer, task, formatted_chunks, req.query)
        chat_latency_ms = int((time.perf_counter() - llm_started) * 1000)
        steps.append(
            {
                "name": "生成结构化回答",
                "tool": (
                    "generate_comparison_table"
                    if task == "multi_document_comparison"
                    else "generate_cited_answer"
                ),
                "detail": f"生成「{task_label}」回答，并保留来源引用。",
                "status": "done",
            }
        )
        steps.append(
            {
                "name": "检查引用可信度",
                "tool": "citation_audit",
                "detail": (
                    f"{citation_check['evidence_state']}，"
                    f"检测到 {citation_check['cited_source_count']} 个有效来源标注。"
                ),
                "status": "done",
            }
        )

        total_latency_ms = int((time.perf_counter() - request_started) * 1000)
        selected_document_ids = sorted(
            {chunk.get("document_id") for chunk in formatted_chunks if chunk.get("document_id") is not None}
        )
        steps.append(
            {
                "name": "记录评估日志",
                "tool": "write_agent_log",
                "detail": "已记录任务类型、检索范围、来源选择和耗时。",
                "status": "done",
            }
        )
        agent_payload = {
            "task": task,
            "task_label": task_label,
            "steps": steps,
            "selected_document_ids": selected_document_ids,
            "selection_reason": source_selection_reason(formatted_chunks),
            "citation_check": citation_check,
        }
        log_metadata = build_retrieval_log_metadata(
            mode="research_agent",
            query=req.query,
            top_k=retrieval_top_k,
            provider=provider,
            chunks=formatted_chunks,
            retrieval_latency_ms=retrieval_latency_ms,
            answer=answer,
            chat_latency_ms=chat_latency_ms,
            total_latency_ms=total_latency_ms,
            session_id=session_id,
            document_id=req.document_id,
        )
        log_metadata["agent"] = agent_payload
        retrieval_log_id = insert_retrieval_log(
            session_id=structured_session_id,
            query=req.query,
            provider=provider,
            top_k=retrieval_top_k,
            results=formatted_chunks,
            latency_ms=retrieval_latency_ms,
            success=True,
            metadata=log_metadata,
        )
        insert_document_citations(
            session_id=structured_session_id,
            retrieval_log_id=retrieval_log_id,
            chunks=formatted_chunks,
        )
        db_conn.commit()

        save_message(session_id, "user", req.query, "[]")
        save_message(session_id, "assistant", answer, json.dumps(formatted_chunks, ensure_ascii=False))

        return {
            "answer": answer,
            "chunks": formatted_chunks,
            "session_id": session_id,
            "agent": agent_payload,
        }
    except HTTPException as exc:
        total_latency_ms = int((time.perf_counter() - request_started) * 1000)
        log_metadata = build_retrieval_log_metadata(
            mode="research_agent",
            query=req.query,
            top_k=req.top_k,
            provider="unavailable",
            chunks=[],
            retrieval_latency_ms=0,
            total_latency_ms=total_latency_ms,
            session_id=session_id,
            document_id=req.document_id,
            error=str(exc.detail),
        )
        log_metadata["agent"] = {"steps": steps, "error": str(exc.detail)}
        insert_retrieval_log(
            session_id=structured_session_id,
            query=req.query,
            provider="unavailable",
            top_k=req.top_k,
            results=[],
            latency_ms=0,
            success=False,
            error=str(exc.detail),
            metadata=log_metadata,
        )
        db_conn.commit()
        raise


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    session_id = req.session_id or "default"
    structured_session_id = ensure_structured_session_id(session_id)
    request_started = time.perf_counter()
    try:
        chunks, provider, latency_ms = run_retrieval(req.query, req.top_k, req.document_id)
        formatted_chunks = format_chunks(chunks)
    except HTTPException as exc:
        log_metadata = build_retrieval_log_metadata(
            mode="chat",
            query=req.query,
            top_k=req.top_k,
            provider="unavailable",
            chunks=[],
            retrieval_latency_ms=0,
            total_latency_ms=int((time.perf_counter() - request_started) * 1000),
            session_id=session_id,
            document_id=req.document_id,
            error=str(exc.detail),
        )
        insert_retrieval_log(
            session_id=structured_session_id,
            query=req.query,
            provider="unavailable",
            top_k=req.top_k,
            results=[],
            latency_ms=0,
            success=False,
            error=str(exc.detail),
            metadata=log_metadata,
        )
        db_conn.commit()
        raise

    llm_started = time.perf_counter()
    if chunks:
        prompt = build_prompt(req.query, chunks)
        answer = chat_with_hunyuan(prompt)
    else:
        answer = "No relevant sources were found. Please try another question."
    chat_latency_ms = int((time.perf_counter() - llm_started) * 1000)
    total_latency_ms = int((time.perf_counter() - request_started) * 1000)

    log_metadata = build_retrieval_log_metadata(
        mode="chat",
        query=req.query,
        top_k=req.top_k,
        provider=provider,
        chunks=formatted_chunks,
        retrieval_latency_ms=latency_ms,
        answer=answer,
        chat_latency_ms=chat_latency_ms,
        total_latency_ms=total_latency_ms,
        session_id=session_id,
        document_id=req.document_id,
    )
    retrieval_log_id = insert_retrieval_log(
        session_id=structured_session_id,
        query=req.query,
        provider=provider,
        top_k=req.top_k,
        results=formatted_chunks,
        latency_ms=latency_ms,
        success=True,
        metadata=log_metadata,
    )
    insert_document_citations(
        session_id=structured_session_id,
        retrieval_log_id=retrieval_log_id,
        chunks=formatted_chunks,
    )
    db_conn.commit()

    save_message(session_id, "user", req.query, "[]")
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


@app.get("/api/retrieval-logs")
def get_retrieval_logs(limit: int = 50, session_id: str | None = None):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")

    structured_session_id = find_structured_session_id(session_id) if session_id else None
    rows = list_retrieval_logs(limit=limit, session_id=structured_session_id)
    return {
        "logs": [serialize_retrieval_log(row) for row in rows],
        "filters": {
            "limit": limit,
            "session_id": session_id,
            "structured_session_id": structured_session_id,
        },
    }


@app.get("/api/retrieval-logs/summary")
def get_retrieval_logs_summary(limit: int = 200, session_id: str | None = None):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")

    structured_session_id = find_structured_session_id(session_id) if session_id else None
    rows = list_retrieval_logs(limit=limit, session_id=structured_session_id)
    return {
        "summary": summarize_retrieval_logs(rows),
        "filters": {
            "limit": limit,
            "session_id": session_id,
            "structured_session_id": structured_session_id,
        },
    }


@app.get("/api/agent/evaluation")
def get_agent_evaluation(limit: int = 200, session_id: str | None = None):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")

    structured_session_id = find_structured_session_id(session_id) if session_id else None
    rows = list_retrieval_logs(limit=limit, session_id=structured_session_id)
    return {
        **build_agent_evaluation(rows),
        "filters": {
            "limit": limit,
            "session_id": session_id,
            "structured_session_id": structured_session_id,
        },
    }


@app.get("/health")
def health():
    """存活探针。

    始终返回 200（进程活着），数据库状态单独放在字段里 ——
    这样才能区分「服务挂了」和「服务活着但数据库连不上」。
    """
    database_status = db_conn.status()
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "database": "postgres" if using_postgres() else "sqlite",
        "database_status": database_status,
    }


if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
