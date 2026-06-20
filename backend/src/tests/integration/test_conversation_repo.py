"""Tests for Phase 0 conversation — current_outline_id."""

import pytest_asyncio

from pptgenius.infrastructure.db.database import Database


class TestConversationOutline:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("conv_out_user")
        conv = await Database(db).create_conversation(u.id)
        return Database(db), conv

    async def test_set_conversation_outline(self, d):
        db_obj, conv = d
        o = await db_obj.create_outline(1, conv.id, "Test Outline")
        assert await db_obj.set_conversation_outline(conv.id, o.id)
        fetched = await db_obj.get_conversation(conv.id)
        assert fetched.current_outline_id == o.id

    async def test_unset_conversation_outline(self, d):
        db_obj, conv = d
        o = await db_obj.create_outline(1, conv.id, "T")
        await db_obj.set_conversation_outline(conv.id, o.id)
        assert await db_obj.set_conversation_outline(conv.id, None)
        fetched = await db_obj.get_conversation(conv.id)
        assert fetched.current_outline_id is None

    async def test_current_outline_id_default_null(self, d):
        db_obj, conv = d
        assert conv.current_outline_id is None

    async def test_set_outline_on_deleted_conv(self, d):
        db_obj, conv = d
        await db_obj.soft_delete_conversation(conv.id)
        o = await db_obj.create_outline(1, conv.id, "Late")
        assert await db_obj.set_conversation_outline(conv.id, o.id) is False
