import pytest_asyncio
from pptgenius.infrastructure.db.models import Conversation, User
from pptgenius.infrastructure.db.repository.conversation import (
    add_tokens,
    archive_conversation,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation_phase,
    update_conversation_title,
)
from pptgenius.infrastructure.db.repository.user import (
    create_user,
    delete_user,
    get_or_create_default_user,
    get_user,
)


class TestUserRepo:
    async def test_create_user(self, db):
        user = await create_user(db, name="test_user")
        assert user.id is not None
        assert user.name == "test_user"

    async def test_get_user(self, db):
        user = await create_user(db, name="alice")
        fetched = await get_user(db, user.id)
        assert fetched is not None
        assert fetched.name == "alice"

    async def test_get_nonexistent_user(self, db):
        assert await get_user(db, 99999) is None

    async def test_get_or_create_default(self, db):
        # 该测试前先确保没有 default 用户
        from pptgenius.infrastructure.db.models import User
        from sqlalchemy import delete

        await db.execute(delete(User))
        await db.commit()

        u1 = await get_or_create_default_user(db)
        u2 = await get_or_create_default_user(db)
        assert u1.id == u2.id
        assert u1.name == "default"

    async def test_delete_user(self, db):
        user = await create_user(db, name="to_delete")
        assert await delete_user(db, user.id) is True
        assert await get_user(db, user.id) is None

    async def test_delete_nonexistent(self, db):
        assert await delete_user(db, 99999) is False


class TestConversationRepo:
    @pytest_asyncio.fixture
    async def user(self, db):
        return await create_user(db, name="conv_test_user")

    async def test_create_conversation(self, db, user):
        conv = await create_conversation(
            db, user_id=user.id, title="Test PPT", workspace_path="/tmp/ws/1"
        )
        assert conv.id is not None
        assert conv.title == "Test PPT"
        assert conv.status == "active"
        assert conv.current_phase == "chat"
        assert conv.total_tokens == 0

    async def test_get_conversation(self, db, user):
        conv = await create_conversation(db, user_id=user.id, title="X")
        fetched = await get_conversation(db, conv.id)
        assert fetched is not None
        assert fetched.title == "X"

    async def test_get_nonexistent(self, db):
        assert await get_conversation(db, 99999) is None

    async def test_list_conversations(self, db, user):
        await create_conversation(db, user_id=user.id, title="A")
        await create_conversation(db, user_id=user.id, title="B")
        convs = await list_conversations(db, user_id=user.id)
        assert len(convs) == 2

    async def test_list_filtered_by_status(self, db, user):
        c1 = await create_conversation(db, user_id=user.id, title="active_one")
        await archive_conversation(db, c1.id)
        await create_conversation(db, user_id=user.id, title="active_two")

        active = await list_conversations(db, user_id=user.id, status="active")
        archived = await list_conversations(db, user_id=user.id, status="archived")

        assert len(active) == 1
        assert active[0].title == "active_two"
        assert len(archived) == 1
        assert archived[0].title == "active_one"

    async def test_update_title(self, db, user):
        conv = await create_conversation(db, user_id=user.id, title="Old")
        ok = await update_conversation_title(db, conv.id, "New")
        assert ok is True
        fetched = await get_conversation(db, conv.id)
        assert fetched.title == "New"

    async def test_update_title_nonexistent(self, db):
        assert await update_conversation_title(db, 99999, "X") is False

    async def test_update_phase(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        await update_conversation_phase(db, conv.id, "outline")
        fetched = await get_conversation(db, conv.id)
        assert fetched.current_phase == "outline"

    async def test_add_tokens(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        await add_tokens(db, conv.id, 500)
        await add_tokens(db, conv.id, 300)
        fetched = await get_conversation(db, conv.id)
        assert fetched.total_tokens == 800

    async def test_add_tokens_nonexistent(self, db):
        assert await add_tokens(db, 99999, 100) is False

    async def test_archive_conversation(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        await archive_conversation(db, conv.id)
        fetched = await get_conversation(db, conv.id)
        assert fetched.status == "archived"

    async def test_delete_conversation(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        assert await delete_conversation(db, conv.id) is True
        assert await get_conversation(db, conv.id) is None

    async def test_delete_nonexistent(self, db):
        assert await delete_conversation(db, 99999) is False
