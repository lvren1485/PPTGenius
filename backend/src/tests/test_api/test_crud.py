"""Integration tests for all CRUD API endpoints.

Uses ``dependency_overrides`` to inject the test DB session (avoids greenlet
issues with ASGI transport + asyncmy driver).
"""

from __future__ import annotations

import io

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete

from pptgenius.api.deps import get_db
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.db.models import (
    Conversation,
    KnowledgeFile,
    Message,
    Outline,
    OutlineSlide,
    Presentation,
    PresentationSlide,
    PresentationSnapshot,
    User,
)
from pptgenius.main import app


# ─── fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(db):
    """httpx async client — injects test DB session via dependency override."""
    app.dependency_overrides[get_db] = _make_override(db)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


def _make_override(db):
    async def override_get_db():
        yield Database(db)
    return override_get_db


@pytest_asyncio.fixture
async def user(client, db):
    d = Database(db)
    u = await d.create_user("api_tester")
    return u


@pytest_asyncio.fixture
async def conv(client, db, user):
    d = Database(db)
    return await d.create_conversation(user.id, "API Test Conversation")


# ─── health ─────────────────────────────────────────────────────────────────


class TestHealth:
    async def test_health(self, client):
        r = await client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["status"] in ("healthy", "degraded")
        assert "db" in data["data"]

    async def test_config(self, client):
        r = await client.get("/api/config")
        assert r.status_code == 200
        data = r.json()
        assert data["data"]["rag"]["algorithm"] == "bm25"
        assert data["data"]["llm"]["provider"] == "deepseek"


# ─── conversations ──────────────────────────────────────────────────────────


class TestConversations:
    async def test_create(self, client, user):
        r = await client.post("/api/conversations", json={"user_id": user.id, "title": "My PPT"})
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["title"] == "My PPT"
        assert data["user_id"] == user.id
        assert data["status"] == "active"
        assert data["id"] > 0

    async def test_list(self, client, user, conv):
        r = await client.get("/api/conversations", params={"user_id": user.id})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 1
        ids = [i["id"] for i in data["items"]]
        assert conv.id in ids

    async def test_get_detail(self, client, conv):
        r = await client.get(f"/api/conversations/{conv.id}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == conv.id
        assert "messages" in data
        assert "outlines" in data
        assert "presentations" in data

    async def test_get_not_found(self, client):
        r = await client.get("/api/conversations/99999")
        assert r.status_code == 404

    async def test_delete(self, client, user, db):
        d = Database(db)
        c = await d.create_conversation(user.id, "ToDelete")
        conv_id = c.id

        r = await client.delete(f"/api/conversations/{conv_id}")
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True

        r2 = await client.get(f"/api/conversations/{conv_id}")
        assert r2.status_code == 404


# ─── outlines ───────────────────────────────────────────────────────────────


class TestOutlines:
    @pytest_asyncio.fixture
    async def outline_with_slides(self, db, user, conv):
        d = Database(db)
        o = await d.create_outline(user.id, conv.id, "Test Outline", slide_count=3)
        await d.create_outline_slide(o.id, 0, "Slide 1", layout_type="title")
        await d.create_outline_slide(o.id, 1, "Slide 2", layout_type="content")
        await d.create_outline_slide(o.id, 2, "Slide 3", layout_type="content")
        return o

    async def test_list_by_user(self, client, user, outline_with_slides):
        r = await client.get("/api/outlines", params={"user_id": user.id})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 1

    async def test_list_by_conversation(self, client, user, conv, outline_with_slides):
        r = await client.get("/api/outlines", params={"user_id": user.id, "conversation_id": conv.id})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert any(o["title"] == "Test Outline" for o in items)

    async def test_get_detail(self, client, outline_with_slides):
        r = await client.get(f"/api/outline/{outline_with_slides.id}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["title"] == "Test Outline"
        assert len(data["slides"]) == 3

    async def test_get_not_found(self, client):
        r = await client.get("/api/outline/99999")
        assert r.status_code == 404

    async def test_get_slides(self, client, outline_with_slides):
        r = await client.get(f"/api/outline/{outline_with_slides.id}/slides")
        assert r.status_code == 200
        slides = r.json()["data"]
        assert len(slides) == 3
        assert slides[0]["title"] == "Slide 1"


# ─── presentations ──────────────────────────────────────────────────────────


class TestPresentations:
    @pytest_asyncio.fixture
    async def pres_with_slides(self, db, user, conv):
        d = Database(db)
        p = await d.create_presentation(user.id, conv.id, outline_id=None)
        await d.create_presentation_slide(p.id, 0, "title_slide")
        await d.create_presentation_slide(p.id, 1, "content_bullet")
        await d.set_presentation_output(p.id, "/tmp/test.pptx", 1024, 2)
        return p

    async def test_list_by_user(self, client, user, pres_with_slides):
        r = await client.get("/api/presentations", params={"user_id": user.id})
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 1

    async def test_list_by_conversation(self, client, user, conv, pres_with_slides):
        r = await client.get("/api/presentations", params={"user_id": user.id, "conversation_id": conv.id})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) >= 1

    async def test_get_detail(self, client, pres_with_slides):
        r = await client.get(f"/api/ppt/{pres_with_slides.id}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "completed"
        assert data["slide_count"] == 2

    async def test_get_not_found(self, client):
        r = await client.get("/api/ppt/99999")
        assert r.status_code == 404

    async def test_get_slides(self, client, pres_with_slides):
        r = await client.get(f"/api/ppt/{pres_with_slides.id}/slides")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["presentation_id"] == pres_with_slides.id
        assert len(data["slides"]) == 2

    async def test_download_not_ready(self, client):
        r = await client.get("/api/ppt/99999/download")
        assert r.status_code == 404


# ─── snapshots ──────────────────────────────────────────────────────────────


class TestSnapshots:
    @pytest_asyncio.fixture
    async def pres_with_snapshots(self, db, user, conv):
        d = Database(db)
        p = await d.create_presentation(user.id, conv.id, outline_id=None)
        await d.create_snapshot(p.id, user.id, conv.id, {"title": "v1"}, {"slides": []})
        await d.create_snapshot(p.id, user.id, conv.id, {"title": "v2"}, {"slides": []})
        return p

    async def test_list_by_presentation(self, client, pres_with_snapshots):
        r = await client.get(f"/api/ppt/{pres_with_snapshots.id}/snapshots")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["presentation_id"] == pres_with_snapshots.id
        assert len(data["snapshots"]) == 2
        versions = [s["version"] for s in data["snapshots"]]
        assert versions == [2, 1]

    async def test_list_not_found(self, client):
        r = await client.get("/api/ppt/99999/snapshots")
        assert r.status_code == 404

    async def test_get_detail(self, client, pres_with_snapshots):
        r = await client.get(f"/api/ppt/{pres_with_snapshots.id}/snapshots")
        snap_id = r.json()["data"]["snapshots"][0]["id"]

        r2 = await client.get(f"/api/snapshots/{snap_id}")
        assert r2.status_code == 200
        data = r2.json()["data"]
        assert "outline_json" in data
        assert "presentation_json" in data

    async def test_snapshot_not_found(self, client):
        r = await client.get("/api/snapshots/99999")
        assert r.status_code == 404


# ─── cost ───────────────────────────────────────────────────────────────────


class TestCost:
    @pytest_asyncio.fixture
    async def conv_with_cost(self, db, user):
        d = Database(db)
        c = await d.create_conversation(user.id, "Cost Test")
        c.estimated_cost = 0.05
        await db.commit()
        await d.create_message(c.id, "assistant", "test", estimated_cost=0.05)
        return c

    async def test_summary(self, client, user, conv_with_cost):
        r = await client.get("/api/cost/summary", params={"user_id": user.id, "days": 30})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["user_id"] == user.id
        assert "total_cost" in data

    async def test_by_date(self, client, user, conv_with_cost):
        r = await client.get("/api/cost/by-date", params={"user_id": user.id, "days": 30})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "items" in data

    async def test_by_conversation(self, client, user, conv_with_cost):
        r = await client.get("/api/cost/by-conversation", params={"user_id": user.id, "days": 30})
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["items"]) >= 1
        titles = [i["title"] for i in data["items"]]
        assert "Cost Test" in titles


# ─── workspace ──────────────────────────────────────────────────────────────


class TestWorkspace:
    async def test_status(self, client, user):
        r = await client.get("/api/workspace/status", params={"user_id": user.id})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "workspace_root" in data
        assert "conversations" in data
        assert "bm25_index" in data


# ─── knowledge ──────────────────────────────────────────────────────────────


class TestKnowledge:
    async def test_upload_and_list_and_delete(self, client, user, conv):
        content = b"Hello, this is a test document for BM25 indexing."
        files = [
            ("files", ("test_api.txt", io.BytesIO(content), "text/plain")),
        ]
        r = await client.post(
            "/api/knowledge/upload",
            data={"user_id": str(user.id), "conversation_id": str(conv.id)},
            files=files,
        )
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        assert len(data["uploaded"]) == 1, data
        file_id = data["uploaded"][0]["id"]

        # List all files for user
        r2 = await client.get("/api/knowledge/files", params={"user_id": user.id})
        assert r2.status_code == 200
        items = r2.json()["data"]["items"]
        assert any(f["id"] == file_id for f in items)

        # List by conversation
        r2b = await client.get(
            "/api/knowledge/files",
            params={"user_id": user.id, "conversation_id": conv.id},
        )
        assert r2b.status_code == 200
        assert any(f["id"] == file_id for f in r2b.json()["data"]["items"])

        # Delete
        r3 = await client.delete(f"/api/knowledge/files/{file_id}")
        assert r3.status_code == 200
        assert r3.json()["data"]["deleted"] is True

        # Verify gone
        r4 = await client.delete(f"/api/knowledge/files/{file_id}")
        assert r4.status_code == 404

    async def test_delete_not_found(self, client):
        r = await client.delete("/api/knowledge/files/99999")
        assert r.status_code == 404
