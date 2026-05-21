"""Tests for database layer."""

from agent.db.engine import get_connection, init_db
from agent.db.conversation import create_session, get_session, add_turn, get_turns, update_session


def test_init_db():
    conn = get_connection()
    init_db(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = [r["name"] for r in tables]
    assert "sessions" in names
    assert "turns" in names
    assert "llm_calls" in names
    assert "tool_calls" in names
    assert "file_registry" in names
    conn.close()


def test_create_session():
    sid = create_session("Test Topic")
    assert sid is not None
    assert len(sid) > 0


def test_get_session():
    sid = create_session("Find Me")
    session = get_session(sid)
    assert session is not None
    assert session["topic"] == "Find Me"
    assert session["status"] == "active"


def test_add_and_get_turns():
    sid = create_session("Turn Test")
    tid = add_turn(sid, "user", "Hello")
    assert tid > 0
    tid2 = add_turn(sid, "agent", "Hi there")
    assert tid2 > 0
    turns = get_turns(sid)
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "agent"


def test_update_session():
    sid = create_session("Update Test")
    update_session(sid, status="completed")
    session = get_session(sid)
    assert session["status"] == "completed"
