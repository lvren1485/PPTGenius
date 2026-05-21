import uuid
from datetime import datetime, timezone

from .engine import get_connection


def create_session(topic: str) -> str:
    """Create a new session and return its ID."""
    session_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (id, created_at, updated_at, topic) VALUES (?, ?, ?, ?)",
            (session_id, now, now, topic),
        )
        conn.commit()
        return session_id
    finally:
        conn.close()


def get_session(session_id: str) -> dict | None:
    """Get session metadata by ID."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_session(session_id: str, **kwargs):
    """Update session fields."""
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [session_id]
    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE sessions SET updated_at = ?, {fields} WHERE id = ?",
            [datetime.now(timezone.utc).isoformat()] + values,
        )
        conn.commit()
    finally:
        conn.close()


def add_turn(session_id: str, role: str, message: str) -> int:
    """Add a conversation turn and return its index."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(turn_index), -1) + 1 FROM turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        turn_index = row[0]
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO turns (session_id, turn_index, role, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, turn_index, role, message, now),
        )
        conn.commit()
        # Return the auto-generated id
        cursor = conn.execute(
            "SELECT id FROM turns WHERE session_id = ? AND turn_index = ?",
            (session_id, turn_index),
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


def get_turns(session_id: str) -> list[dict]:
    """Get all turns for a session, ordered by turn_index."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_index",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_llm_call(
    call_id: str,
    session_id: str,
    turn_id: int,
    model: str,
    system_prompt: str | None = None,
    response: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int = 0,
):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO llm_calls
               (id, session_id, turn_id, model, system_prompt, response,
                prompt_tokens, completion_tokens, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (call_id, session_id, turn_id, model, system_prompt, response,
             prompt_tokens, completion_tokens, duration_ms, now),
        )
        conn.commit()
    finally:
        conn.close()


def save_tool_call(
    session_id: str,
    turn_id: int,
    tool_name: str,
    tool_input: str,
    tool_output: str | None = None,
    duration_ms: int = 0,
    status: str = "success",
):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO tool_calls
               (session_id, turn_id, tool_name, tool_input, tool_output,
                duration_ms, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, turn_id, tool_name, tool_input, tool_output,
             duration_ms, status, now),
        )
        conn.commit()
    finally:
        conn.close()
