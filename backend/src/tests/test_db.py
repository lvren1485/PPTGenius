import pytest_asyncio
from sqlalchemy import delete

from pptgenius.infrastructure.db.models import User
from pptgenius.infrastructure.db.repository.conversation import (
    create_conversation,
    get_conversation,
    list_conversations,
    soft_delete_conversation,
    update_conversation_phase,
    update_conversation_title,
)
from pptgenius.infrastructure.db.repository.user import (
    create_user,
    delete_user,
    get_or_create_default_user,
    get_user,
)
from pptgenius.infrastructure.db.repository.message import (
    create_human_message,
    create_message,
    get_messages_by_conversation,
    trim_messages,
)
from pptgenius.infrastructure.db.repository.outline import (
    create_outline,
    create_outline_slide,
    get_outline,
    get_slides_by_outline_id,
    list_outlines_by_conversation,
    list_outlines_by_user,
    soft_delete_outline,
    update_outline_eval,
    update_outline_status,
)
from pptgenius.infrastructure.db.repository.knowledge import (
    create_chunk,
    create_knowledge_file,
    delete_knowledge_file,
    get_chunk_by_id,
    get_knowledge_file,
    get_all_chunks_for_user,
    list_chunks_by_file,
    list_knowledge_files,
)
from pptgenius.infrastructure.db.repository.web_resource import (
    create_web_resource,
    find_by_url,
    get_all_web_resources,
    delete_web_resource,
    get_web_resource,
)


class TestUserRepo:
    async def test_create(self, db):
        u = await create_user(db, "alice")
        assert u.id is not None
        assert u.name == "alice"

    async def test_get(self, db):
        u = await create_user(db, "bob")
        fetched = await get_user(db, u.id)
        assert fetched.name == "bob"

    async def test_get_nonexistent(self, db):
        assert await get_user(db, 99999) is None

    async def test_get_or_create_default(self, db):
        await db.execute(delete(User))
        await db.commit()
        u1 = await get_or_create_default_user(db)
        u2 = await get_or_create_default_user(db)
        assert u1.id == u2.id
        assert u1.name == "default"

    async def test_delete(self, db):
        u = await create_user(db, "temp")
        assert await delete_user(db, u.id) is True
        assert await get_user(db, u.id) is None

    async def test_delete_nonexistent(self, db):
        assert await delete_user(db, 99999) is False


class TestConversationRepo:
    @pytest_asyncio.fixture
    async def user(self, db):
        return await create_user(db, "conv_user")

    async def test_create(self, db, user):
        conv = await create_conversation(db, user_id=user.id, title="PPT")
        assert conv.id is not None
        assert conv.title == "PPT"
        assert conv.status == "active"
        assert conv.workspace_path == f"./data/workspace/{conv.id}"

    async def test_get(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        fetched = await get_conversation(db, conv.id)
        assert fetched is not None

    async def test_get_nonexistent(self, db):
        assert await get_conversation(db, 99999) is None

    async def test_get_deleted_returns_none(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        await soft_delete_conversation(db, conv.id)
        assert await get_conversation(db, conv.id) is None

    async def test_list_excludes_deleted(self, db, user):
        await create_conversation(db, user_id=user.id, title="visible")
        deleted = await create_conversation(db, user_id=user.id, title="hidden")
        await soft_delete_conversation(db, deleted.id)
        convs = await list_conversations(db, user_id=user.id)
        assert len(convs) == 1
        assert convs[0].title == "visible"

    async def test_update_title(self, db, user):
        conv = await create_conversation(db, user_id=user.id, title="Old")
        assert await update_conversation_title(db, conv.id, "New")
        assert (await get_conversation(db, conv.id)).title == "New"

    async def test_update_title_deleted(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        await soft_delete_conversation(db, conv.id)
        assert await update_conversation_title(db, conv.id, "X") is False

    async def test_update_phase(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        await update_conversation_phase(db, conv.id, "outline")
        assert (await get_conversation(db, conv.id)).current_phase == "outline"

    async def test_soft_delete(self, db, user):
        conv = await create_conversation(db, user_id=user.id)
        assert await soft_delete_conversation(db, conv.id) is True
        assert await soft_delete_conversation(db, 99999) is False


class TestMessageRepo:
    @pytest_asyncio.fixture
    async def user(self, db):
        return await create_user(db, "msg_user")

    @pytest_asyncio.fixture
    async def conv(self, db, user):
        return await create_conversation(db, user_id=user.id)

    async def test_create_message(self, db, conv):
        msg = await create_message(db, conv.id, role="user", content="hello")
        assert msg.idx == 1
        assert msg.role == "user"
        assert msg.content == "hello"

    async def test_idx_auto_increment(self, db, conv):
        m1 = await create_message(db, conv.id, role="user", content="a")
        m2 = await create_message(db, conv.id, role="assistant", content="b")
        assert m1.idx == 1
        assert m2.idx == 2

    async def test_create_human_message(self, db, conv):
        msg = await create_human_message(db, conv.id, content="hi")
        assert msg.role == "user"
        assert msg.content_type == "text"

    async def test_token_accumulation(self, db, conv):
        await create_message(db, conv.id, role="user", content="q", token_count=100)
        await create_message(db, conv.id, role="assistant", content="a", token_count=500)
        fetched = await get_conversation(db, conv.id)
        assert fetched.total_tokens == 600

    async def test_get_messages_by_conversation(self, db, conv):
        await create_message(db, conv.id, role="user", content="q1")
        await create_message(db, conv.id, role="assistant", content="a1")
        msgs = await get_messages_by_conversation(db, conv.id)
        assert len(msgs) == 2

    async def test_trim_messages(self, db, conv):
        await create_message(db, conv.id, role="user", content="m1")  # idx=1
        await create_message(db, conv.id, role="assistant", content="m2")  # idx=2
        await create_message(db, conv.id, role="user", content="m3")  # idx=3

        deleted = await trim_messages(db, conv.id, before_idx=3)
        assert deleted == 2
        msgs = await get_messages_by_conversation(db, conv.id)
        assert len(msgs) == 1
        assert msgs[0].content == "m3"


class TestOutlineRepo:
    @pytest_asyncio.fixture
    async def user(self, db):
        return await create_user(db, "outline_user")

    @pytest_asyncio.fixture
    async def conv(self, db, user):
        return await create_conversation(db, user_id=user.id)

    async def test_create_outline(self, db, user, conv):
        o = await create_outline(db, user.id, conv.id, "My Outline", slide_count=5)
        assert o.id is not None
        assert o.status == "draft"
        assert o.version == 1

    async def test_get_outline(self, db, user, conv):
        o = await create_outline(db, user.id, conv.id, "Test")
        fetched = await get_outline(db, o.id)
        assert fetched.title == "Test"

    async def test_get_deleted_returns_none(self, db, user, conv):
        o = await create_outline(db, user.id, conv.id, "X")
        await soft_delete_outline(db, o.id)
        assert await get_outline(db, o.id) is None

    async def test_list_by_conversation(self, db, user, conv):
        await create_outline(db, user.id, conv.id, "V1")
        await create_outline(db, user.id, conv.id, "V2")
        outlines = await list_outlines_by_conversation(db, conv.id)
        assert len(outlines) == 2

    async def test_list_by_user(self, db, user, conv):
        await create_outline(db, user.id, conv.id, "A")
        result = await list_outlines_by_user(db, user.id)
        assert len(result) >= 1

    async def test_update_status(self, db, user, conv):
        o = await create_outline(db, user.id, conv.id, "S")
        assert await update_outline_status(db, o.id, "approved")
        assert (await get_outline(db, o.id)).status == "approved"

    async def test_update_eval(self, db, user, conv):
        o = await create_outline(db, user.id, conv.id, "E")
        assert await update_outline_eval(db, o.id, 0.85)
        assert (await get_outline(db, o.id)).eval_score == 0.85

    async def test_soft_delete(self, db, user, conv):
        o = await create_outline(db, user.id, conv.id, "D")
        assert await soft_delete_outline(db, o.id)

    async def test_outline_slides(self, db, user, conv):
        o = await create_outline(db, user.id, conv.id, "Slides")
        s1 = await create_outline_slide(db, o.id, 0, "Slide 1")
        s2 = await create_outline_slide(db, o.id, 1, "Slide 2")
        slides = await get_slides_by_outline_id(db, o.id)
        assert len(slides) == 2


class TestKnowledgeRepo:
    @pytest_asyncio.fixture
    async def user(self, db):
        return await create_user(db, "knowledge_user")

    async def test_create_and_get(self, db, user):
        kf = await create_knowledge_file(
            db, user.id, "test.pdf", "/tmp/test.pdf", "pdf", file_size=1024
        )
        fetched = await get_knowledge_file(db, kf.id)
        assert fetched.filename == "test.pdf"

    async def test_list_files(self, db, user):
        await create_knowledge_file(db, user.id, "a.pdf", "/tmp/a.pdf", "pdf")
        await create_knowledge_file(db, user.id, "b.docx", "/tmp/b.docx", "docx")
        files = await list_knowledge_files(db, user.id)
        assert len(files) == 2

    async def test_list_filtered(self, db, user):
        await create_knowledge_file(db, user.id, "a.pdf", "/tmp/a.pdf", "pdf")
        await create_knowledge_file(db, user.id, "b.docx", "/tmp/b.docx", "docx")
        pdfs = await list_knowledge_files(db, user.id, file_type="pdf")
        assert len(pdfs) == 1

    async def test_delete_cascades_chunks(self, db, user):
        kf = await create_knowledge_file(db, user.id, "c.pdf", "/tmp/c.pdf", "pdf")
        await create_chunk(db, kf.id, 0, "chunk text")
        await create_chunk(db, kf.id, 1, "chunk text 2")

        # chunk exists before delete
        chunks = await list_chunks_by_file(db, kf.id)
        assert len(chunks) == 2

        await delete_knowledge_file(db, kf.id)

        # file and chunks gone
        assert await get_knowledge_file(db, kf.id) is None
        chunks_after = await list_chunks_by_file(db, kf.id)
        assert len(chunks_after) == 0

    async def test_get_chunk_by_id(self, db, user):
        kf = await create_knowledge_file(db, user.id, "d.txt", "/tmp/d.txt", "txt")
        c = await create_chunk(db, kf.id, 0, "hello world")
        fetched = await get_chunk_by_id(db, c.id)
        assert fetched.chunk_text == "hello world"

    async def test_get_all_chunks_for_user(self, db, user):
        kf = await create_knowledge_file(db, user.id, "e.txt", "/tmp/e.txt", "txt")
        await create_chunk(db, kf.id, 0, "chunk A")
        await create_chunk(db, kf.id, 1, "chunk B")

        all_chunks = await get_all_chunks_for_user(db, user.id)
        assert len(all_chunks) == 2


class TestWebResourceRepo:
    @pytest_asyncio.fixture
    async def user(self, db):
        return await create_user(db, "web_user")

    async def test_create_and_get(self, db, user):
        wr = await create_web_resource(
            db, user.id, "https://example.com", title="Example", source_domain="example.com"
        )
        fetched = await get_web_resource(db, wr.id)
        assert fetched.title == "Example"

    async def test_find_by_url(self, db, user):
        await create_web_resource(db, user.id, "https://x.com/page")
        found = await find_by_url(db, "https://x.com/page")
        assert found is not None
        assert await find_by_url(db, "https://x.com/other") is None

    async def test_get_all(self, db, user):
        await create_web_resource(db, user.id, "https://a.com")
        await create_web_resource(db, user.id, "https://b.com")
        all_wr = await get_all_web_resources(db, user.id)
        assert len(all_wr) == 2

    async def test_delete(self, db, user):
        wr = await create_web_resource(db, user.id, "https://del.com")
        assert await delete_web_resource(db, wr.id) is True
        assert await get_web_resource(db, wr.id) is None
