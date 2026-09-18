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


def postgres_column_exists(conn, table: str, column: str) -> bool:
    cursor = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ANY (current_schemas(false))
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def configure_migration_timeouts(conn) -> None:
    if not using_postgres():
        return
    try:
        conn.execute("SET statement_timeout = '120s'")
        conn.execute("SET lock_timeout = '10s'")
    except Exception as exc:
        conn.rollback()
        print(f"[db] unable to configure migration timeouts: {exc}")


def add_column_if_missing(conn, table: str, column: str, definition: str) -> bool:
    if using_postgres():
        if postgres_column_exists(conn, table, column):
            return False

        try:
            conn.execute(
                f"ALTER TABLE {quote_identifier(table)} "
                f"ADD COLUMN {quote_identifier(column)} {definition}"
            )
            conn.commit()
            print(f"[db] added missing column {table}.{column}")
            return True
        except Exception as exc:
            conn.rollback()
            if postgres_column_exists(conn, table, column):
                return False
            print(f"[db] skipped migration for {table}.{column}: {exc}")
            return False

    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True
    return False


def apply_migrations(conn) -> None:
    js = json_type()
    ts = timestamp_type()
    add_column_if_missing(conn, "document_chunks", "embedding", js)
    add_column_if_missing(conn, "document_chunks", "embedding_model", "TEXT")
    add_column_if_missing(conn, "document_chunks", "embedding_updated_at", ts)
    add_column_if_missing(conn, "retrieval_logs", "metadata", js)


def create_indexes(conn) -> None:
    execute_many(
        conn,
        [
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)",
            "CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id)",
            "CREATE INDEX IF NOT EXISTS idx_retrieval_logs_session_id ON retrieval_logs(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_document_citations_session_id ON document_citations(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_document_citations_document_id ON document_citations(document_id)",
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
                f"""CREATE TABLE IF NOT EXISTS document_files (
                    document_id INTEGER PRIMARY KEY,
                    file_name TEXT,
                    content_type TEXT,
                    file_size INTEGER,
                    data BYTEA,
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP
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
                    embedding {js},
                    embedding_model TEXT,
                    embedding_updated_at {ts},
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
                    metadata {js},
                    created_at {ts} DEFAULT CURRENT_TIMESTAMP
                )""",
                f"""CREATE TABLE IF NOT EXISTS document_citations (
                    id {pk},
                    session_id INTEGER,
                    message_id INTEGER,
                    retrieval_log_id INTEGER,
                    document_id INTEGER,
                    chunk_id INTEGER,
                    chunk_index INTEGER,
                    source_label TEXT,
                    source_title TEXT,
                    page_start INTEGER,
                    page_end INTEGER,
                    metadata {js},
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
        conn.commit()
        configure_migration_timeouts(conn)
        apply_migrations(conn)
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
    if using_postgres():
        cursor = conn.execute(
            """
            INSERT INTO messages (session_id, role, content, sources, metadata)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (session_id, role, content, sources, metadata),
        )
        return cursor

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
