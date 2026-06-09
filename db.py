"""Database schema and helpers for ZhiYu."""

from __future__ import annotations

import sqlite3
from os import environ
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from config import DATABASE_PATH, DATABASE_URL


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
                    "Use the Supabase shared pooler URL instead."
                ) from exc
            raise

    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path, check_same_thread=False)


def placeholder() -> str:
    return "%s" if using_postgres() else "?"


def json_type() -> str:
    return "JSONB" if using_postgres() else "TEXT"


def timestamp_type() -> str:
    return "TIMESTAMPTZ" if using_postgres() else "DATETIME"


def primary_key_type() -> str:
    return "SERIAL PRIMARY KEY" if using_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"


def execute_many(conn, statements: list[str]) -> None:
    for statement in statements:
        conn.execute(statement)


def create_indexes(conn) -> None:
    execute_many(
        conn,
        [
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)",
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_doc_id ON document_chunks(doc_id)",
            "CREATE INDEX IF NOT EXISTS idx_retrieval_logs_session_id ON retrieval_logs(session_id)",
        ],
    )


def init_db() -> None:
    pk = primary_key_type()
    ts = timestamp_type()
    js = json_type()

    conn = connect_db()
    try:
        execute_many(
            conn,
            [
                f"""CREATE TABLE IF NOT EXISTS users (
                    id {pk},
                    external_id TEXT UNIQUE,
                    display_name TEXT,
                    email TEXT,
                    role TEXT DEFAULT 'user',
                    metadata {js},
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
                f"""CREATE TABLE IF NOT EXISTS sessions (
                    id {pk},
                    user_id INTEGER,
                    title TEXT,
                    status TEXT DEFAULT 'active',
                    metadata {js},
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
                f"""CREATE TABLE IF NOT EXISTS messages (
                    id {pk},
                    session_id INTEGER,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources {js},
                    metadata {js},
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
                f"""CREATE TABLE IF NOT EXISTS documents (
                    id {pk},
                    title TEXT NOT NULL,
                    author TEXT,
                    year TEXT,
                    source_type TEXT,
                    file_name TEXT,
                    file_type TEXT,
                    file_url TEXT,
                    file_size INTEGER,
                    status TEXT DEFAULT 'pending',
                    metadata {js},
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
                f"""CREATE TABLE IF NOT EXISTS document_chunks (
                    id {pk},
                    document_id INTEGER,
                    chunk_index INTEGER,
                    content TEXT NOT NULL,
                    page_start INTEGER,
                    page_end INTEGER,
                    section_title TEXT,
                    char_start INTEGER,
                    char_end INTEGER,
                    source_title TEXT,
                    embedding_id TEXT,
                    metadata {js},
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
                f"""CREATE TABLE IF NOT EXISTS retrieval_logs (
                    id {pk},
                    session_id INTEGER,
                    message_id INTEGER,
                    query TEXT NOT NULL,
                    provider TEXT,
                    top_k INTEGER,
                    results {js},
                    latency_ms INTEGER,
                    success BOOLEAN DEFAULT TRUE,
                    error TEXT,
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
                f"""CREATE TABLE IF NOT EXISTS conversations (
                    id {pk},
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    sources TEXT,
                    timestamp {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
            ],
        )
        create_indexes(conn)
        conn.commit()
    finally:
        conn.close()


def insert_message(
    conn,
    session_id: int | None,
    role: str,
    content: str,
    sources: str,
    metadata: str | None = None,
) -> Any:
    mark = placeholder()
    cursor = conn.execute(
        "INSERT INTO messages (session_id, role, content, sources, metadata) "
        f"VALUES ({mark}, {mark}, {mark}, {mark}, {mark})",
        (session_id, role, content, sources, metadata),
    )
    return cursor


def ensure_default_session(conn, external_session_id: str) -> int | None:
    if not using_postgres():
        return None

    cursor = conn.execute(
        "SELECT id FROM sessions WHERE metadata->>'external_session_id' = %s LIMIT 1",
        (external_session_id,),
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor = conn.execute(
        "INSERT INTO sessions (title, metadata) VALUES (%s, %s::jsonb) RETURNING id",
        ("Chat", f'{{"external_session_id": "{external_session_id}"}}'),
    )
    return cursor.fetchone()[0]
