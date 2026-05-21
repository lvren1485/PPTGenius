import sqlite3
from pathlib import Path

from ..config import config


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection to the agent database."""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None):
    """Create all tables if they don't exist."""
    close = conn is None
    if conn is None:
        conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                topic       TEXT,
                status      TEXT NOT NULL DEFAULT 'active',
                output_path TEXT,
                report_path TEXT
            );

            CREATE TABLE IF NOT EXISTS turns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL REFERENCES sessions(id),
                turn_index  INTEGER NOT NULL,
                role        TEXT NOT NULL,
                message     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                UNIQUE(session_id, turn_index)
            );

            CREATE TABLE IF NOT EXISTS llm_calls (
                id              TEXT PRIMARY KEY,
                session_id      TEXT NOT NULL REFERENCES sessions(id),
                turn_id         INTEGER NOT NULL REFERENCES turns(id),
                model           TEXT NOT NULL,
                system_prompt   TEXT,
                user_prompt     TEXT,
                response        TEXT,
                prompt_tokens   INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                duration_ms     INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL REFERENCES sessions(id),
                turn_id     INTEGER NOT NULL REFERENCES turns(id),
                llm_call_id TEXT REFERENCES llm_calls(id),
                tool_name   TEXT NOT NULL,
                tool_input  TEXT NOT NULL,
                tool_output TEXT,
                duration_ms INTEGER DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'success'
            );

            CREATE TABLE IF NOT EXISTS file_registry (
                path        TEXT PRIMARY KEY,
                mtime       REAL NOT NULL,
                hash        TEXT NOT NULL,
                file_size   INTEGER DEFAULT 0,
                file_type   TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                error_msg   TEXT,
                processed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS _imports (
                table_name  TEXT PRIMARY KEY,
                source_file TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                row_count   INTEGER DEFAULT 0,
                columns     TEXT
            );
        """)
        conn.commit()
    finally:
        if close:
            conn.close()
