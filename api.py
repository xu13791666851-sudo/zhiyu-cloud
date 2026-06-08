"""Knowledge retrieval for ZhiYu.

Retrieval priority:
1. Dify dataset retrieval
2. RAGFlow retrieval
3. Local keyword fallback
"""

from __future__ import annotations

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
    USE_DIFY_RETRIEVAL,
    USE_RAGFLOW_RETRIEVAL,
)


Chunk = dict[str, Any]


def _normalize_chunk(content: str, doc: str, similarity: float | int | None) -> Chunk | None:
    content = (content or "").strip()
    if not content:
        return None
    return {
        "content": content,
        "doc": doc or "unknown",
        "similarity": float(similarity or 0.0),
    }


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

            if chunk:
                chunks.append(chunk)

        chunks.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        print(f"[Dify] retrieved {len(chunks)} chunks for: {query[:40]}")
        return chunks or None
    except Exception as exc:
        print(f"[Dify] retrieval failed: {exc}")
        traceback.print_exc()
        return None


def retrieve_local(query: str, top_k: int = 5) -> list[Chunk]:
    if not KNOWLEDGE_BASE:
        return []

    stopwords = {
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
        "什么",
        "如何",
        "为什么",
        "关于",
    }
    keywords = [char for char in query if char.strip() and char not in stopwords]

    scored: list[tuple[int, Chunk]] = []
    for chunk in KNOWLEDGE_BASE:
        content = chunk.get("content", "")
        score = sum(content.count(keyword) for keyword in keywords)
        if score > 0:
            normalized = _normalize_chunk(
                content,
                chunk.get("doc") or chunk.get("source") or chunk.get("title") or "local",
                chunk.get("similarity") or score,
            )
            if normalized:
                scored.append((score, normalized))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def retrieve(query: str, top_k: int = 5) -> list[Chunk]:
    print(f"[retrieve] query={query[:40]!r}, top_k={top_k}")

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

    print("[retrieve] using local keyword fallback")
    return retrieve_local(query, top_k)
