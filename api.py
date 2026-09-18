"""Knowledge retrieval for ZhiYu.

Retrieval priority:
1. Dify dataset retrieval
2. RAGFlow retrieval
3. Uploaded document chunks in the database
4. Local keyword fallback from knowledge_base.json
"""

from __future__ import annotations

import json
import re
import traceback
from typing import Any

import requests

from config import (
    DIFY_API_KEY,
    DIFY_API_URL,
    DIFY_DATASET_ID,
    KNOWLEDGE_BASE,
    RAGFLOW_API_KEY,
    RAGFLOW_API_URL,
    RAGFLOW_KB_ID,
    EMBEDDING_MIN_SIMILARITY,
    USE_DIFY_RETRIEVAL,
    USE_RAGFLOW_RETRIEVAL,
)
from db import connect_db
from embeddings import cosine_similarity, embed_text, embeddings_configured


Chunk = dict[str, Any]
EMBEDDING_CANDIDATE_MULTIPLIER = 4
EMBEDDING_MIN_CANDIDATES = 20
IDEAL_CHUNK_MIN_CHARS = 180
IDEAL_CHUNK_MAX_CHARS = 1800


CJK_STOP_CHARS = {
    "的",
    "了",
    "和",
    "是",
    "在",
    "有",
    "与",
    "及",
    "或",
    "吗",
    "呢",
    "中",
    "为",
    "对",
    "把",
    "被",
}


def _normalize_chunk(content: str, doc: str, similarity: float | int | None) -> Chunk | None:
    content = (content or "").strip()
    if not content:
        return None
    return {
        "content": content,
        "doc": doc or "unknown",
        "similarity": float(similarity or 0.0),
    }


def _with_provider(chunk: Chunk | None, provider: str) -> Chunk | None:
    if not chunk:
        return None
    chunk["provider"] = provider
    return chunk


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _compact_search_text(text: str) -> str:
    parts = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", (text or "").lower())
    return "".join(parts)


def _cjk_ngrams(text: str, min_size: int = 2, max_size: int = 4) -> list[str]:
    terms: list[str] = []
    for sequence in re.findall(r"[\u4e00-\u9fff]+", text):
        upper = min(max_size, len(sequence))
        for size in range(min_size, upper + 1):
            terms.extend(sequence[index : index + size] for index in range(0, len(sequence) - size + 1))
    return terms


def _build_query_terms(query: str) -> list[str]:
    normalized = query.strip().lower()
    if not normalized:
        return []

    compact_query = _compact_search_text(normalized)
    token_terms = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}", normalized)
    cjk_ngrams = _cjk_ngrams(normalized)
    cjk_chars = [
        char
        for char in normalized
        if "\u4e00" <= char <= "\u9fff" and char not in CJK_STOP_CHARS
    ]
    return _unique_preserve_order([compact_query, *token_terms, *cjk_ngrams, *cjk_chars])


def _term_weight(term: str) -> float:
    if not term:
        return 0.0
    if re.fullmatch(r"[\u4e00-\u9fff]", term):
        return 0.35
    if re.fullmatch(r"[\u4e00-\u9fff]+", term):
        return min(8.0, max(1.0, len(term) * 1.4))
    return min(6.0, max(1.0, len(term) * 0.8))


def _score_text(text: str, terms: list[str], *, exact_query: str, title: str = "") -> float:
    haystack = (text or "").lower()
    title_haystack = (title or "").lower()
    if not haystack and not title_haystack:
        return 0

    compact_text = _compact_search_text(haystack)
    compact_title = _compact_search_text(title_haystack)
    compact_query = _compact_search_text(exact_query)

    score = 0.0
    if compact_query and compact_query in compact_text:
        score += max(18.0, len(compact_query) * 2.2)
    if compact_query and compact_query in compact_title:
        score += max(28.0, len(compact_query) * 3.2)

    for term in terms:
        if not term.strip():
            continue
        weight = _term_weight(term)
        if weight <= 0:
            continue

        content_hits = haystack.count(term) or compact_text.count(term)
        title_hits = title_haystack.count(term) or compact_title.count(term)
        if not content_hits and not title_hits:
            continue
        score += content_hits * weight
        score += title_hits * weight * 2.8
    return score


def _keyword_coverage(text: str, terms: list[str]) -> float:
    meaningful_terms = [term for term in terms if len(term) >= 2]
    if not meaningful_terms:
        return 0.0
    haystack = _compact_search_text(text)
    hits = sum(1 for term in meaningful_terms if term in haystack)
    return hits / len(meaningful_terms)


def _length_quality(text: str) -> float:
    length = len((text or "").strip())
    if not length:
        return 0.0
    if IDEAL_CHUNK_MIN_CHARS <= length <= IDEAL_CHUNK_MAX_CHARS:
        return 1.0
    if length < IDEAL_CHUNK_MIN_CHARS:
        return max(0.2, length / IDEAL_CHUNK_MIN_CHARS)
    return max(0.3, IDEAL_CHUNK_MAX_CHARS / length)


def _rerank_score(
    *,
    embedding_score: float,
    keyword_score: float,
    coverage: float,
    title_score: float,
    section_score: float,
    length_quality: float,
) -> float:
    return (
        embedding_score * 0.70
        + min(keyword_score / 40.0, 1.0) * 0.10
        + coverage * 0.08
        + min(title_score / 20.0, 1.0) * 0.06
        + min(section_score / 12.0, 1.0) * 0.04
        + length_quality * 0.02
    )


def retrieve_from_ragflow(query: str, top_k: int = 5) -> list[Chunk] | None:
    if not USE_RAGFLOW_RETRIEVAL:
        return None

    try:
        url = f"{RAGFLOW_API_URL.rstrip('/')}/retrieval"
        headers = {
            "Authorization": f"Bearer {RAGFLOW_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "question": query,
            "dataset_ids": [RAGFLOW_KB_ID],
            "page_size": top_k,
            "similarity_threshold": 0.0,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0 or "data" not in data:
            print(f"[RAGFlow] API returned unexpected payload: {data}")
            return None

        inner = data["data"]
        raw_chunks = inner.get("chunks", []) if isinstance(inner, dict) else []
        chunks: list[Chunk] = []
        for item in raw_chunks:
            chunk = _normalize_chunk(
                item.get("content_with_weight") or item.get("content", ""),
                item.get("document_keyword")
                or item.get("doc_name")
                or item.get("doc")
                or "unknown",
                item.get("similarity"),
            )
            chunk = _with_provider(chunk, "ragflow")
            if chunk:
                chunks.append(chunk)

        chunks.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        print(f"[RAGFlow] retrieved {len(chunks)} chunks for: {query[:40]}")
        return chunks or None
    except Exception as exc:
        print(f"[RAGFlow] retrieval failed: {exc}")
        return None


def retrieve_from_dify(query: str, top_k: int = 5) -> list[Chunk] | None:
    if not USE_DIFY_RETRIEVAL:
        return None

    try:
        url = f"{DIFY_API_URL.rstrip('/')}/datasets/{DIFY_DATASET_ID}/retrieve"
        headers = {
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "top_k": top_k,
            "score_threshold": 0.0,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        records = data.get("records", [])
        chunks: list[Chunk] = []
        for record in records:
            if "content" in record:
                chunk = _normalize_chunk(
                    record.get("content", ""),
                    record.get("doc_name") or record.get("title") or "unknown",
                    record.get("score"),
                )
            elif "segment" in record:
                segment = record.get("segment", {})
                document = record.get("document", {})
                chunk = _normalize_chunk(
                    segment.get("content", ""),
                    document.get("name") or segment.get("document_id", "unknown"),
                    record.get("score"),
                )
            else:
                chunk = None

            chunk = _with_provider(chunk, "dify")
            if chunk:
                chunks.append(chunk)

        chunks.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        print(f"[Dify] retrieved {len(chunks)} chunks for: {query[:40]}")
        return chunks or None
    except Exception as exc:
        print(f"[Dify] retrieval failed: {exc}")
        traceback.print_exc()
        return None


def _parse_embedding(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [float(item) for item in parsed] if isinstance(parsed, list) else []
    return []


def retrieve_from_document_embeddings(
    query: str,
    top_k: int = 5,
    *,
    document_id: int | None = None,
) -> list[Chunk] | None:
    if not embeddings_configured():
        return None

    query_vector = embed_text(query)
    if not query_vector:
        return None

    conn = connect_db()
    try:
        cursor = conn.cursor()
        document_filter = f" AND dc.document_id = {int(document_id)}" if document_id is not None else ""
        cursor.execute(
            f"""
            SELECT
                dc.content,
                dc.document_id,
                dc.chunk_index,
                dc.section_title,
                dc.page_start,
                dc.page_end,
                dc.embedding,
                dc.embedding_model,
                d.title,
                d.file_name,
                d.source_type
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.status = 'parsed'
              AND dc.embedding IS NOT NULL
              {document_filter}
            ORDER BY dc.document_id DESC, dc.chunk_index ASC
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    scored_rows: list[tuple[float, Chunk]] = []
    terms = _build_query_terms(query)
    exact_query = query.strip().lower()
    candidate_limit = max(top_k * EMBEDDING_CANDIDATE_MULTIPLIER, EMBEDDING_MIN_CANDIDATES)
    for row in rows:
        (
            content,
            document_id,
            chunk_index,
            section_title,
            page_start,
            page_end,
            embedding,
            embedding_model,
            title,
            file_name,
            source_type,
        ) = row
        embedding_score = cosine_similarity(query_vector, _parse_embedding(embedding))
        if embedding_score < EMBEDDING_MIN_SIMILARITY:
            continue

        display_title = title or file_name or "uploaded document"
        searchable_title = " ".join(
            value for value in [display_title, section_title or "", source_type or ""] if value
        )
        keyword_score = _score_text(content or "", terms, exact_query=exact_query, title=searchable_title)
        title_score = _score_text("", terms, exact_query=exact_query, title=display_title)
        section_score = _score_text("", terms, exact_query=exact_query, title=section_title or "")
        coverage = _keyword_coverage(f"{searchable_title}\n{content or ''}", terms)
        length_quality = _length_quality(content or "")
        final_score = _rerank_score(
            embedding_score=embedding_score,
            keyword_score=keyword_score,
            coverage=coverage,
            title_score=title_score,
            section_score=section_score,
            length_quality=length_quality,
        )
        section_suffix = f" / {section_title}" if section_title else ""
        page_suffix = ""
        if page_start and page_end:
            page_suffix = f" (pp. {page_start}-{page_end})" if page_start != page_end else f" (p. {page_start})"
        normalized = _normalize_chunk(content or "", f"{display_title}{section_suffix}{page_suffix}", final_score)
        if normalized:
            normalized["document_id"] = document_id
            normalized["chunk_index"] = chunk_index
            normalized["source_type"] = source_type
            normalized["section_title"] = section_title
            normalized["page_start"] = page_start
            normalized["page_end"] = page_end
            normalized["embedding_model"] = embedding_model
            normalized["embedding_score"] = round(embedding_score, 6)
            normalized["keyword_score"] = round(keyword_score, 4)
            normalized["coverage_score"] = round(coverage, 4)
            normalized["title_score"] = round(title_score, 4)
            normalized["section_score"] = round(section_score, 4)
            normalized["length_quality"] = round(length_quality, 4)
            normalized["rerank_score"] = round(final_score, 6)
            normalized["provider"] = "document_embeddings"
            scored_rows.append((final_score, normalized))

    if not scored_rows:
        return None

    candidates = sorted(scored_rows, key=lambda item: item[0], reverse=True)[:candidate_limit]
    ranked = [chunk for _, chunk in candidates[:top_k]]
    scope = f" document_id={document_id}" if document_id is not None else ""
    print(f"[document_embeddings] retrieved {len(ranked)} chunks from {len(candidates)} candidates{scope} for: {query[:40]}")
    return ranked


def retrieve_from_document_chunks(
    query: str,
    top_k: int = 5,
    *,
    document_id: int | None = None,
) -> list[Chunk] | None:
    embedding_results = retrieve_from_document_embeddings(query, top_k, document_id=document_id)
    if embedding_results:
        return embedding_results

    terms = _build_query_terms(query)
    if not terms:
        return None

    conn = connect_db()
    try:
        cursor = conn.cursor()
        document_filter = f" AND dc.document_id = {int(document_id)}" if document_id is not None else ""
        cursor.execute(
            f"""
            SELECT
                dc.content,
                dc.document_id,
                dc.chunk_index,
                dc.section_title,
                dc.page_start,
                dc.page_end,
                d.title,
                d.file_name,
                d.source_type
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE d.status = 'parsed'
              {document_filter}
            ORDER BY dc.document_id DESC, dc.chunk_index ASC
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    scored_rows: list[tuple[float, Chunk]] = []
    exact_query = query.strip().lower()
    for row in rows:
        content, document_id, chunk_index, section_title, page_start, page_end, title, file_name, source_type = row
        display_title = title or file_name or "uploaded document"
        searchable_title = " ".join(
            value for value in [display_title, section_title or "", source_type or ""] if value
        )
        score = _score_text(content or "", terms, exact_query=exact_query, title=searchable_title)
        if score <= 0:
            continue

        section_suffix = f" / {section_title}" if section_title else ""
        page_suffix = ""
        if page_start and page_end:
            page_suffix = f" (pp. {page_start}-{page_end})" if page_start != page_end else f" (p. {page_start})"
        doc_label = f"{display_title}{section_suffix}{page_suffix}"
        normalized = _normalize_chunk(content or "", doc_label, score)
        if normalized:
            normalized["document_id"] = document_id
            normalized["chunk_index"] = chunk_index
            normalized["source_type"] = source_type
            normalized["section_title"] = section_title
            normalized["page_start"] = page_start
            normalized["page_end"] = page_end
            normalized["provider"] = "document_chunks"
            scored_rows.append((score, normalized))

    if not scored_rows:
        return None

    max_score = max(score for score, _ in scored_rows) or 1
    ranked: list[Chunk] = []
    for score, chunk in sorted(scored_rows, key=lambda item: item[0], reverse=True)[:top_k]:
        chunk["similarity"] = round(score / max_score, 4)
        ranked.append(chunk)
    scope = f" document_id={document_id}" if document_id is not None else ""
    print(f"[document_chunks] retrieved {len(ranked)} chunks{scope} for: {query[:40]}")
    return ranked


def retrieve_local(query: str, top_k: int = 5, *, document_id: int | None = None) -> list[Chunk]:
    chunk_results = retrieve_from_document_chunks(query, top_k, document_id=document_id)
    if chunk_results:
        return chunk_results

    if document_id is not None:
        return []

    if not KNOWLEDGE_BASE:
        return []

    keywords = _build_query_terms(query)
    exact_query = query.strip().lower()
    scored: list[tuple[float, Chunk]] = []

    for chunk in KNOWLEDGE_BASE:
        content = chunk.get("content", "")
        title = chunk.get("doc") or chunk.get("source") or chunk.get("title") or "local"
        score = _score_text(content, keywords, exact_query=exact_query, title=title)
        if score <= 0:
            continue

        normalized = _normalize_chunk(
            content,
            title,
            chunk.get("similarity") or score,
        )
        if normalized:
            normalized["provider"] = "knowledge_base"
            scored.append((score, normalized))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def retrieve(query: str, top_k: int = 5, document_id: int | None = None) -> list[Chunk]:
    print(f"[retrieve] query={query[:40]!r}, top_k={top_k}, document_id={document_id}")

    if document_id is not None:
        print("[retrieve] using uploaded document scope")
        return retrieve_local(query, top_k, document_id=document_id)

    if USE_DIFY_RETRIEVAL:
        chunks = retrieve_from_dify(query, top_k)
        if chunks:
            return chunks
        print("[retrieve] Dify returned no chunks; trying RAGFlow")

    if USE_RAGFLOW_RETRIEVAL:
        chunks = retrieve_from_ragflow(query, top_k)
        if chunks:
            return chunks
        print("[retrieve] RAGFlow returned no chunks; using local fallback")

    print("[retrieve] using uploaded documents and local keyword fallback")
    return retrieve_local(query, top_k)
