"""Embedding helpers for ZhiYu retrieval."""

from __future__ import annotations

import math
from typing import Any

import requests

from config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    USE_EMBEDDING_RETRIEVAL,
)


def embeddings_configured() -> bool:
    return bool(USE_EMBEDDING_RETRIEVAL and EMBEDDING_API_KEY and EMBEDDING_BASE_URL and EMBEDDING_MODEL)


def embedding_status() -> dict[str, Any]:
    return {
        "enabled": bool(USE_EMBEDDING_RETRIEVAL),
        "configured": embeddings_configured(),
        "base_url": EMBEDDING_BASE_URL,
        "model": EMBEDDING_MODEL,
        "batch_size": EMBEDDING_BATCH_SIZE,
        "has_api_key": bool(EMBEDDING_API_KEY),
    }


def embed_texts(texts: list[str]) -> list[list[float]]:
    clean_texts = [(text or "").strip() for text in texts]
    if not clean_texts:
        return []
    if not embeddings_configured():
        raise RuntimeError("Embedding retrieval is not configured")

    url = f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {EMBEDDING_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": clean_texts,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()

    records = data.get("data")
    if not isinstance(records, list):
        raise RuntimeError(f"Embedding API returned unexpected payload: {data}")

    vectors_by_index: dict[int, list[float]] = {}
    for index, record in enumerate(records):
        record_index = record.get("index", index) if isinstance(record, dict) else index
        embedding = record.get("embedding") if isinstance(record, dict) else None
        if not isinstance(embedding, list):
            raise RuntimeError(f"Embedding API returned a record without embedding: {record}")
        vectors_by_index[int(record_index)] = [float(value) for value in embedding]

    return [vectors_by_index[index] for index in range(len(clean_texts))]


def embed_text(text: str) -> list[float]:
    vectors = embed_texts([text])
    return vectors[0] if vectors else []


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
