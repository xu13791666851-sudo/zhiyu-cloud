"""FastAPI backend for ZhiYu."""

from __future__ import annotations

import json
from typing import Any, Optional

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    ALLOWED_ORIGINS,
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
