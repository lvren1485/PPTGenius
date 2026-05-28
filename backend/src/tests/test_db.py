import pytest_asyncio
from sqlalchemy import delete

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.db.models import User


class TestUserRepo:
    async def test_create(self, db):
        d = Database(db)
        u = await d.create_user("alice", "secret")
        assert u.id is not None
        assert u.name == "alice"
        assert u.password == "secret"

    async def test_get(self, db):
        d = Database(db)
        u = await d.create_user("bob")
        assert (await d.get_user(u.id)).name == "bob"

    async def test_get_nonexistent(self, db):
        assert await Database(db).get_user(99999) is None

    async def test_get_or_create_default(self, db):
        from pptgenius.infrastructure.db.models import (
            Conversation, KnowledgeChunk, KnowledgeFile, Message,
            Outline, OutlineSlide, Presentation, PresentationSlide, PresentationSnapshot,
        )

        d = Database(db)
        # Delete in FK dependency order (children before parents)
        for model in [
            PresentationSlide, PresentationSnapshot,  # → presentations
            OutlineSlide,                              # → outlines
            KnowledgeChunk,                            # → knowledge_files
            Message,                                   # → conversations
            Presentation,                              # → conversations, users
            Outline,                                   # → conversations, users
            Conversation,                              # → users
            KnowledgeFile,                             # → users
        ]:
            await db.execute(delete(model))
        await db.commit()
        await db.execute(delete(User))
        await db.commit()
        u1 = await d.get_or_create_default_user()
        u2 = await d.get_or_create_default_user()
        assert u1.id == u2.id
        assert u1.name == "default"

    async def test_delete(self, db):
        d = Database(db)
        u = await d.create_user("temp")
        assert await d.delete_user(u.id) is True
        assert await d.get_user(u.id) is None

    async def test_delete_nonexistent(self, db):
        assert await Database(db).delete_user(99999) is False


class TestConversationRepo:
    @pytest_asyncio.fixture
    async def user(self, db):
        return await Database(db).create_user("conv_user")

    async def test_create(self, db, user):
        conv = await Database(db).create_conversation(user.id, "PPT")
        assert conv.workspace_path == f"./data/workspace/{conv.id}"

    async def test_soft_delete_and_filter(self, db, user):
        d = Database(db)
        visible = await d.create_conversation(user.id, "visible")
        deleted = await d.create_conversation(user.id, "hidden")
        await d.soft_delete_conversation(deleted.id)
        convs = await d.list_conversations(user.id)
        assert len(convs) == 1
        assert convs[0].id == visible.id

    async def test_deleted_returns_none_on_get(self, db, user):
        d = Database(db)
        conv = await d.create_conversation(user.id)
        await d.soft_delete_conversation(conv.id)
        assert await d.get_conversation(conv.id) is None

    async def test_update_title_and_phase(self, db, user):
        d = Database(db)
        conv = await d.create_conversation(user.id, "Old")
        assert await d.update_conversation_title(conv.id, "New")
        assert await d.update_conversation_phase(conv.id, "outline")
        fetched = await d.get_conversation(conv.id)
        assert fetched.title == "New"
        assert fetched.current_phase == "outline"


class TestMessageRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("msg_user")
        conv = await Database(db).create_conversation(u.id)
        return Database(db), conv

    async def test_idx_and_cost_accumulation(self, db, d):
        db_obj, conv = d
        m1 = await db_obj.create_message(conv.id, "user", "q", estimated_cost=0.001)
        m2 = await db_obj.create_message(conv.id, "assistant", "a", estimated_cost=0.005)
        assert m1.idx == 1
        assert m2.idx == 2
        assert abs((await db_obj.get_conversation(conv.id)).estimated_cost - 0.006) < 1e-9

    async def test_create_human_message(self, db, d):
        db_obj, conv = d
        msg = await db_obj.create_human_message(conv.id, "hi")
        assert msg.role == "user"

    async def test_get_and_trim(self, db, d):
        db_obj, conv = d
        await db_obj.create_message(conv.id, "user", "m1")
        await db_obj.create_message(conv.id, "assistant", "m2")
        await db_obj.create_message(conv.id, "user", "m3")
        assert len(await db_obj.get_messages_by_conversation(conv.id)) == 3
        deleted = await db_obj.trim_messages(conv.id, before_idx=3)
        assert deleted == 2
        msgs = await db_obj.get_messages_by_conversation(conv.id)
        assert len(msgs) == 1
        assert msgs[0].content == "m3"


class TestOutlineRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("outline_user")
        conv = await Database(db).create_conversation(u.id)
        return Database(db), u, conv

    async def test_crud(self, db, d):
        db_obj, user, conv = d
        o = await db_obj.create_outline(user.id, conv.id, "My Outline", 5)
        assert o.status == "draft"
        assert o.version == 1

        fetched = await db_obj.get_outline(o.id)
        assert fetched.title == "My Outline"

        await db_obj.soft_delete_outline(o.id)
        assert await db_obj.get_outline(o.id) is None

    async def test_list_by_user(self, db, d):
        db_obj, user, conv = d
        await db_obj.create_outline(user.id, conv.id, "A")
        await db_obj.create_outline(user.id, conv.id, "B")
        assert len(await db_obj.list_outlines_by_user(user.id)) >= 2

    async def test_eval_and_version(self, db, d):
        db_obj, user, conv = d
        o = await db_obj.create_outline(user.id, conv.id, "E")
        await db_obj.update_outline_eval(o.id, 0.85)
        await db_obj.increment_outline_version(o.id)
        fetched = await db_obj.get_outline(o.id)
        assert fetched.eval_score == 0.85
        assert fetched.version == 2

    async def test_slides(self, db, d):
        db_obj, user, conv = d
        o = await db_obj.create_outline(user.id, conv.id, "Slides")
        await db_obj.create_outline_slide(o.id, 0, "Slide A")
        await db_obj.create_outline_slide(o.id, 1, "Slide B")
        slides = await db_obj.get_slides_by_outline_id(o.id)
        assert len(slides) == 2


class TestPresentationRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("pres_user")
        conv = await Database(db).create_conversation(u.id)
        return Database(db), u, conv

    async def test_create_and_get(self, db, d):
        db_obj, user, conv = d
        pres = await db_obj.create_presentation(user.id, conv.id)
        assert pres.status == "pending"
        fetched = await db_obj.get_presentation(pres.id)
        assert fetched is not None

    async def test_list_by_user(self, db, d):
        db_obj, user, conv = d
        await db_obj.create_presentation(user.id, conv.id)
        await db_obj.create_presentation(user.id, conv.id)
        assert len(await db_obj.list_presentations_by_user(user.id)) >= 2

    async def test_set_output(self, db, d):
        db_obj, user, conv = d
        pres = await db_obj.create_presentation(user.id, conv.id)
        await db_obj.set_presentation_output(pres.id, "/tmp/out.pptx", 1024, 5)
        fetched = await db_obj.get_presentation(pres.id)
        assert fetched.file_path == "/tmp/out.pptx"
        assert fetched.status == "completed"

    async def test_slides_with_agent_output(self, db, d):
        db_obj, user, conv = d
        pres = await db_obj.create_presentation(user.id, conv.id)
        slide = await db_obj.create_presentation_slide(pres.id, 0, "title_slide")
        await db_obj.set_slide_agent_output(pres.id, 0, "text", {"title": "Hello"})
        await db_obj.set_slide_agent_output(pres.id, 0, "layout", {"color": "blue"})

        fetched = await db_obj.get_presentation_slide(slide.id)
        assert fetched.agent_outputs["text"] == {"title": "Hello"}
        assert fetched.agent_outputs["layout"] == {"color": "blue"}

    async def test_slide_status_and_retry(self, db, d):
        db_obj, user, conv = d
        pres = await db_obj.create_presentation(user.id, conv.id)
        slide = await db_obj.create_presentation_slide(pres.id, 0, "content")
        assert (await db_obj.increment_slide_retry(slide.id)) == 1
        await db_obj.update_slide_status(pres.id, 0, "failed", "timeout")
        fetched = await db_obj.get_presentation_slide(slide.id)
        assert fetched.status == "failed"
        assert fetched.retry_count == 1


class TestKnowledgeRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("kn_user")
        return Database(db), u

    async def test_file_crud(self, db, d):
        db_obj, user = d
        kf = await db_obj.create_knowledge_file(user.id, "test.pdf", "/tmp/test.pdf", "pdf", 1024)
        assert kf.filename == "test.pdf"
        assert await db_obj.get_knowledge_file(kf.id) is not None

    async def test_delete_cascades_chunks(self, db, d):
        db_obj, user = d
        kf = await db_obj.create_knowledge_file(user.id, "c.pdf", "/tmp/c.pdf", "pdf")
        await db_obj.create_chunk(kf.id, 0, "text")
        assert len(await db_obj.list_chunks_by_file(kf.id)) == 1
        await db_obj.delete_knowledge_file(kf.id)
        assert await db_obj.get_knowledge_file(kf.id) is None
        assert len(await db_obj.list_chunks_by_file(kf.id)) == 0

    async def test_chunk_by_id(self, db, d):
        db_obj, user = d
        kf = await db_obj.create_knowledge_file(user.id, "d.txt", "/tmp/d.txt", "txt")
        c = await db_obj.create_chunk(kf.id, 0, "hello")
        assert (await db_obj.get_chunk_by_id(c.id)).chunk_text == "hello"

    async def test_chunks_for_user(self, db, d):
        db_obj, user = d
        kf = await db_obj.create_knowledge_file(user.id, "e.txt", "/tmp/e.txt", "txt")
        await db_obj.create_chunk(kf.id, 0, "A")
        await db_obj.create_chunk(kf.id, 1, "B")
        assert len(await db_obj.get_all_chunks_for_user(user.id)) == 2


class TestSnapshotRepo:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("snap_user")
        conv = await Database(db).create_conversation(u.id)
        pres = await Database(db).create_presentation(u.id, conv.id)
        return Database(db), u, conv, pres

    async def test_create_and_list(self, db, d):
        db_obj, user, conv, pres = d
        s1 = await db_obj.create_snapshot(
            pres.id, user.id, conv.id,
            outline_json={"title": "V1", "slides": []},
            presentation_json={"slides": [{"idx": 0, "text": "hello"}]},
        )
        assert s1.version == 1

        s2 = await db_obj.create_snapshot(
            pres.id, user.id, conv.id,
            outline_json={"title": "V2", "slides": []},
            presentation_json={"slides": [{"idx": 0, "text": "world"}]},
        )
        assert s2.version == 2

        snaps = await db_obj.list_snapshots_by_presentation(pres.id)
        assert len(snaps) == 2

    async def test_get_and_latest(self, db, d):
        db_obj, user, conv, pres = d
        await db_obj.create_snapshot(
            pres.id, user.id, conv.id,
            outline_json={"title": "A"}, presentation_json={},
        )
        await db_obj.create_snapshot(
            pres.id, user.id, conv.id,
            outline_json={"title": "B"}, presentation_json={},
        )
        latest = await db_obj.get_latest_snapshot(pres.id)
        assert latest is not None
        assert latest.version == 2
        assert latest.outline_json["title"] == "B"

        fetched = await db_obj.get_snapshot(latest.id)
        assert fetched is not None

    async def test_delete(self, db, d):
        db_obj, user, conv, pres = d
        s = await db_obj.create_snapshot(
            pres.id, user.id, conv.id,
            outline_json={}, presentation_json={},
        )
        assert await db_obj.delete_snapshot(s.id) is True
        assert await db_obj.get_snapshot(s.id) is None
