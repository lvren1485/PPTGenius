"""Tests for outline_snapshots + presentation_snapshots — version mirrors entity version."""

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
            outline_version=outline.version,
            outline_json={"title": "V1", "sections": []},
        )
        assert snap.id is not None
        assert snap.version == outline.version
        assert snap.outline_json == {"title": "V1", "sections": []}

    async def test_version_mirrors_outline_version(self, d):
        db_obj, user, conv, outline = d
        await db_obj.increase_outline_version(outline.id)
        await db_obj.increase_outline_version(outline.id)
        outline_v2 = await db_obj.get_outline(outline.id)  # version = 2
        snap = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_version=outline_v2.version,
            outline_json={"v": 2},
        )
        assert snap.version == 2

    async def test_get_outline_snapshot(self, d):
        db_obj, user, conv, outline = d
        snap = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_version=outline.version,
            outline_json={},
        )
        fetched = await db_obj.get_outline_snapshot(snap.id)
        assert fetched is not None

    async def test_list_outline_snapshots(self, d):
        db_obj, user, conv, outline = d
        await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_version=1, outline_json={"n": 1},
        )
        await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_version=2, outline_json={"n": 2},
        )
        snaps = await db_obj.list_outline_snapshots(outline.id)
        assert len(snaps) == 2
        assert snaps[0].version > snaps[1].version  # desc order

    async def test_get_latest_outline_snapshot(self, d):
        db_obj, user, conv, outline = d
        await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_version=1, outline_json={"v": 1},
        )
        await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_version=2, outline_json={"v": 2},
        )
        latest = await db_obj.get_latest_outline_snapshot(outline.id)
        assert latest.version == 2

    async def test_delete_outline_snapshot(self, d):
        db_obj, user, conv, outline = d
        snap = await db_obj.create_outline_snapshot(
            outline.id, user.id, conv.id,
            outline_version=outline.version,
            outline_json={},
        )
        assert await db_obj.delete_outline_snapshot(snap.id)
        assert await db_obj.get_outline_snapshot(snap.id) is None
