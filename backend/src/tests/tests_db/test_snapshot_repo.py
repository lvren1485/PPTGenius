"""Tests for outline_snapshots CRUD."""

import pytest_asyncio

from pptgenius.infrastructure.db.database import Database


class TestOutlineSnapshotRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("osnap_user")
        conv = await Database(db).create_conversation(u.id)
        o = await Database(db).create_outline(u.id, conv.id, "Snap Test")
        return Database(db), u, conv, o

    async def test_create_outline_snapshot(self, d):
        db_obj, user, conv, outline = d
        snap = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_json={"title": "V1", "sections": []},
        )
        assert snap.id is not None
        assert snap.version == 1
        assert snap.outline_json == {"title": "V1", "sections": []}

    async def test_version_auto_increment(self, d):
        db_obj, user, conv, outline = d
        s1 = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id, outline_json={"v": 1},
        )
        s2 = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id, outline_json={"v": 2},
        )
        assert s1.version == 1
        assert s2.version == 2

    async def test_get_outline_snapshot(self, d):
        db_obj, user, conv, outline = d
        snap = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id, outline_json={},
        )
        fetched = await db_obj.get_outline_snapshot(snap.id)
        assert fetched is not None

    async def test_list_outline_snapshots(self, d):
        db_obj, user, conv, outline = d
        await db_obj.create_outline_snapshot(outline.id, user.id, conv.id, outline_json={"n": 1})
        await db_obj.create_outline_snapshot(outline.id, user.id, conv.id, outline_json={"n": 2})
        snaps = await db_obj.list_outline_snapshots(outline.id)
        assert len(snaps) == 2
        assert snaps[0].version > snaps[1].version  # desc order

    async def test_get_latest_outline_snapshot(self, d):
        db_obj, user, conv, outline = d
        await db_obj.create_outline_snapshot(outline.id, user.id, conv.id, outline_json={"v": 1})
        await db_obj.create_outline_snapshot(outline.id, user.id, conv.id, outline_json={"v": 2})
        latest = await db_obj.get_latest_outline_snapshot(outline.id)
        assert latest.version == 2

    async def test_delete_outline_snapshot(self, d):
        db_obj, user, conv, outline = d
        snap = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id, outline_json={},
        )
        assert await db_obj.delete_outline_snapshot(snap.id)
        assert await db_obj.get_outline_snapshot(snap.id) is None
