"""FastAPI backend for ZhiYu."""

from __future__ import annotations

import json
import sqlite3
from os import environ
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api import retrieve
from config import (
    ALLOWED_ORIGINS,
    DATABASE_PATH,
    DATABASE_URL,
    HUNYUAN_API_KEY,
    HUNYUAN_BASE_URL,
    HUNYUAN_MODEL,
)


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


def using_postgres() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def normalized_database_url() -> str:
    if not DATABASE_URL:
        return DATABASE_URL

    parsed = urlparse(DATABASE_URL)
    if not parsed.hostname or not parsed.hostname.endswith(".supabase.co"):
        return DATABASE_URL

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunparse(parsed._replace(query=urlencode(query)))


def connect_db():
    if using_postgres():
        import psycopg

        try:
            return psycopg.connect(
                normalized_database_url(),
                connect_timeout=int(environ.get("DATABASE_CONNECT_TIMEOUT", "10")),
                prepare_threshold=None,
            )
        except psycopg.OperationalError as exc:
            if "Network is unreachable" in str(exc) and "supabase.co" in DATABASE_URL:
                raise RuntimeError(
                    "Supabase direct database URLs are IPv6-only on the free plan. "
                    "Use the Supabase shared pooler URL instead, for example "
                    "postgresql://postgres.<project-ref>:<password>@aws-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
                ) from exc
            raise

    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path, check_same_thread=False)


def placeholder() -> str:
    return "%s" if using_postgres() else "?"


def init_db() -> None:
    conn = connect_db()
    try:
        if using_postgres():
            conn.execute(
                """CREATE TABLE IF NOT EXISTS conversations (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    sources TEXT,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )"""
            )
        else:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    sources TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )"""
            )
        conn.commit()
    finally:
        conn.close()


init_db()
db_conn = connect_db()


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
    if not HUNYUAN_API_KEY:
        return "LLM is not configured. Please set HUNYUAN_API_KEY in .env."

    try:
        url = f"{HUNYUAN_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {HUNYUAN_API_KEY}",
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
    db_conn.commit()


@app.post("/api/retrieve")
def api_retrieve(req: RetrieveRequest):
    chunks = retrieve(req.query, req.top_k)
    return {"chunks": format_chunks(chunks)}


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    chunks = retrieve(req.query, req.top_k)

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
