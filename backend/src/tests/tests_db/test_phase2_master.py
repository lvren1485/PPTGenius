"""Tests for Phase 2 — Master Agent tools (perception + structure)."""

import pytest

from pptgenius.infrastructure.db.database import Database


class TestPerceptionTools:
    @pytest.mark.asyncio
    async def test_get_conversation_status(self, db):
        d = Database(db)
        u = await d.create_user("per_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test Outline")
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_get_conversation_status(d, conv.id)
        result = await tool.ainvoke({})
        assert result["conversation_id"] == conv.id
        assert result["current_outline_id"] == o.id
        assert len(result["outlines"]) >= 1

    @pytest.mark.asyncio
    async def test_switch_outline(self, db):
        d = Database(db)
        u = await d.create_user("sw_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Switch Target")
        tool = make_switch_outline(d, conv.id)
        result = await tool.ainvoke({"outline_id": o.id})
        assert f"已切换到大纲" in result
        conv2 = await d.get_conversation(conv.id)
        assert conv2.current_outline_id == o.id

    @pytest.mark.asyncio
    async def test_switch_outline_null(self, db):
        d = Database(db)
        u = await d.create_user("sw2_user")
        conv = await d.create_conversation(u.id)
        tool = make_switch_outline(d, conv.id)
        result = await tool.ainvoke({"outline_id": None})
        assert "已取消选中大纲" in result

    @pytest.mark.asyncio
    async def test_get_outline(self, db):
        d = Database(db)
        u = await d.create_user("go_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Get Outline")
        sec = await d.create_outline_section(o.id, 1, "Sec 1")
        await d.create_outline_slide(o.id, 1, "Slide 1", section_id=sec.id)
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_get_outline(d, conv.id)
        result = await tool.ainvoke({})
        assert result["title"] == "Get Outline"
        assert len(result["sections"]) == 1

    @pytest.mark.asyncio
    async def test_get_outline_no_selection(self, db):
        d = Database(db)
        u = await d.create_user("go2_user")
        conv = await d.create_conversation(u.id)
        tool = make_get_outline(d, conv.id)
        result = await tool.ainvoke({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_outline_slide(self, db):
        d = Database(db)
        u = await d.create_user("gos_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Slide Detail")
        sl = await d.create_outline_slide(o.id, 1, "Detail Slide",
                                           content_json={"main_points": ["A", "B"]})
        tool = make_get_outline_slide(d, conv.id)
        result = await tool.ainvoke({"slide_id": sl.id})
        assert result["title"] == "Detail Slide"
        assert result["content_json"]["main_points"] == ["A", "B"]

    @pytest.mark.asyncio
    async def test_list_styles(self, db):
        d = Database(db)
        u = await d.create_user("ls_user")
        conv = await d.create_conversation(u.id)
        await d.create_style(name="test_blue", label="Test Blue",
                             colors_json={}, chart_colors_json=[], fonts_json={})
        tool = make_search_styles(d, conv.id)
        result = await tool.ainvoke({"query": "blue"})
        assert len(result) >= 1
        assert any(s["name"] == "test_blue" for s in result)


class TestStructureTools:
    @pytest.mark.asyncio
    async def test_write_outline_structure(self, db):
        d = Database(db)
        u = await d.create_user("ws_user")
        conv = await d.create_conversation(u.id)
        tool = make_write_outline_structure(d, conv.id)
        result = await tool.ainvoke({
            "title": "AI报告",
            "sections": [
                {"section_index": 1, "title": "引言", "description": "背景", "slide_number": 3},
                {"section_index": 2, "title": "方法", "description": "技术", "slide_number": 4},
            ],
        })
        assert "已创建大纲" in result
        conv2 = await d.get_conversation(conv.id)
        assert conv2.current_outline_id is not None
        outline = await d.get_outline(conv2.current_outline_id)
        slides = await d.get_slides_by_outline_id(outline.id)
        assert any(s.layout_type == "title" for s in slides)
        assert any(s.layout_type == "thanks" for s in slides)
        # Section slides should be pre-created (section + content per section)
        assert any(s.layout_type == "section" for s in slides)
        assert any(s.layout_type == "content" for s in slides)
        # Each section should have slides assigned
        sections = await d.get_sections_by_outline_id(outline.id)
        assert len(sections) == 2
        for sec in sections:
            sec_slides = [s for s in slides if s.section_id == sec.id]
            assert len(sec_slides) >= 2
        # Verify slide_number is respected: 3 + 4 = 7 body slides
        body = [s for s in slides if s.layout_type in ("section", "content") and s.section_id]
        assert len(body) == 7

    @pytest.mark.asyncio
    async def test_modify_rename(self, db):
        d = Database(db)
        u = await d.create_user("mo2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Modify Test")
        sl = await d.create_outline_slide(o.id, 1, "Old Name")
        await d.set_conversation_outline(conv.id, o.id)
        tool = make_modify_outline_structure(d, conv.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke({"operations": [{"op": "rename", "slide_id": sl.id, "new_title": "New Name"}]})
        assert "rename×1" in r["summary"]
        assert (await d.get_outline_slide(sl.id)).title == "New Name"

    @pytest.mark.asyncio
    async def test_modify_delete_simple(self, db):
        d = Database(db)
        u = await d.create_user("md2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        await d.create_outline_slide(o.id, 1, "Keep")
        s2 = await d.create_outline_slide(o.id, 2, "Delete Me")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": s2.id}]})
        assert len(await d.get_slides_by_outline_id(o.id)) == 1

    @pytest.mark.asyncio
    async def test_modify_delete_with_merge(self, db):
        d = Database(db)
        u = await d.create_user("dm2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Merge Test")
        s1 = await d.create_outline_slide(o.id, 1, "A", content_json={"main_points": ["A1"]})
        s2 = await d.create_outline_slide(o.id, 2, "B", content_json={"main_points": ["B1"]})
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "delete", "target_id": s2.id, "merge_id": s1.id}]})
        assert "占位" in r["summary"]
        s1f = await d.get_outline_slide(s1.id)
        assert "B1" in str(s1f.content_json)
        assert s1f.status == "merge"

    @pytest.mark.asyncio
    async def test_modify_insert_simple(self, db):
        d = Database(db)
        u = await d.create_user("mi2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        s1 = await d.create_outline_slide(o.id, 1, "First")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "insert", "after_id": s1.id}]})
        assert len(await d.get_slides_by_outline_id(o.id)) == 2

    @pytest.mark.asyncio
    async def test_modify_insert_split(self, db):
        d = Database(db)
        u = await d.create_user("ms2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        s1 = await d.create_outline_slide(o.id, 1, "Original")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "insert", "after_id": s1.id, "is_copy": True}]})
        s1f = await d.get_outline_slide(s1.id)
        assert s1f.status == "split"
        slides = await d.get_slides_by_outline_id(o.id)
        assert len(slides) == 2

    @pytest.mark.asyncio
    async def test_modify_move(self, db):
        d = Database(db)
        u = await d.create_user("mm2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        sec = await d.create_outline_section(o.id, 1, "S1")
        s1 = await d.create_outline_slide(o.id, 1, "A", section_id=sec.id)
        s2 = await d.create_outline_slide(o.id, 2, "B", section_id=sec.id)
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "move", "target_id": s1.id, "after_id": s2.id}]})
        slides = await d.get_slides_by_outline_id(o.id)
        assert slides[-1].id == s1.id

    @pytest.mark.asyncio
    async def test_modify_move_cross_section_rejected(self, db):
        d = Database(db)
        u = await d.create_user("mx2_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        sec1 = await d.create_outline_section(o.id, 1, "S1")
        sec2 = await d.create_outline_section(o.id, 2, "S2")
        s1 = await d.create_outline_slide(o.id, 1, "A", section_id=sec1.id)
        s2 = await d.create_outline_slide(o.id, 2, "B", section_id=sec2.id)
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke(
            {"operations": [{"op": "move", "target_id": s1.id, "after_id": s2.id}]})
        assert "is_change_section=true" in r.get("summary", "")

    @pytest.mark.asyncio
    async def test_modify_duplicate_ids_rejected(self, db):
        d = Database(db)
        u = await d.create_user("dup_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test")
        s1 = await d.create_outline_slide(o.id, 1, "X")
        await d.set_conversation_outline(conv.id, o.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke({"operations": [
            {"op": "rename", "slide_id": s1.id, "new_title": "A"},
            {"op": "rename", "slide_id": s1.id, "new_title": "B"},
        ]})
        assert "重复" in r["error"]

    @pytest.mark.asyncio
    async def test_modify_no_outline_error(self, db):
        d = Database(db)
        u = await d.create_user("moe2_user")
        conv = await d.create_conversation(u.id)
        tool = make_modify_outline_structure(d, conv.id)
        r = await make_modify_outline_structure(d, conv.id).ainvoke({"operations": [{"op": "rename", "slide_id": 99999, "new_title": "X"}]})
        assert "error" in r


class TestWriteThenReadOutline:
    """Verify current_outline_id persists after write_outline_structure."""

    @pytest.mark.asyncio
    async def test_write_then_conv_status_sees_outline(self, db):
        d = Database(db)
        u = await d.create_user("wtro_user")
        conv = await d.create_conversation(u.id)

        write_tool = make_write_outline_structure(d, conv.id)
        await write_tool.ainvoke({
            "title": "Test",
            "sections": [{"section_index": 1, "title": "S1", "description": "", "slide_number": 2}],
        })

        # Immediately check conv_status
        status_tool = make_get_conversation_status(d, conv.id)
        status = await status_tool.ainvoke({})
        assert status["current_outline_id"] is not None, \
            f"current_outline_id should be set after write_outline, got {status['current_outline_id']}"
        assert len(status["outlines"]) >= 1, \
            f"outlines should include the newly created one, got {len(status['outlines'])}"

    @pytest.mark.asyncio
    async def test_write_then_get_outline_sees_it(self, db):
        d = Database(db)
        u = await d.create_user("wtro2_user")
        conv = await d.create_conversation(u.id)

        write_tool = make_write_outline_structure(d, conv.id)
        await write_tool.ainvoke({
            "title": "Test2",
            "sections": [{"section_index": 1, "title": "Ch1", "description": "", "slide_number": 2}],
        })

        get_tool = make_get_outline(d, conv.id)
        result = await get_tool.ainvoke({})
        assert "error" not in result, f"get_outline should succeed, got: {result}"
        assert result["title"] == "Test2"
        assert len(result["sections"]) == 1

    @pytest.mark.asyncio
    async def test_current_outline_id_survives_commit_roundtrip(self, db):
        d = Database(db)
        u = await d.create_user("wtro3_user")
        conv = await d.create_conversation(u.id)

        write_tool = make_write_outline_structure(d, conv.id)
        await write_tool.ainvoke({
            "title": "RT",
            "sections": [{"section_index": 1, "title": "X", "description": "", "slide_number": 2}],
        })

        # Simulate what happens between turns: commit + re-read
        await db.commit()

        # Read from fresh session perspective
        conv2 = await d.get_conversation(conv.id)
        assert conv2.current_outline_id is not None, \
            f"current_outline_id lost after commit: {conv2.current_outline_id}"

        outlines = await d.list_outlines_by_conversation(conv.id)
        assert len(outlines) >= 1, \
            f"outlines lost after commit: {len(outlines)}"


class TestConvStatusAfterWrite:
    """Simulate API flow: write_outline in one call, conv_status in another."""

    @pytest.mark.asyncio
    async def test_conv_status_sees_outline_across_turns(self, db):
        """Turn 1: write_outline → Turn 2: conv_status (same session, simulating API flow)."""
        d = Database(db)
        u = await d.create_user("csaw_user")
        conv = await d.create_conversation(u.id)

        # Turn 1: create outline (like Master calling write_outline_structure)
        w = make_write_outline_structure(d, conv.id)
        r = await w.ainvoke({
            "title": "Cross-Turn Test",
            "sections": [{"section_index": 1, "title": "S1", "description": "", "slide_number": 2}],
        })
        assert "已创建大纲" in r

        # Simulate what the API does after tool returns: persist messages, snapshot, etc.
        # create_message (simulating _persist_tool_messages)
        msg = await d.create_message(conv.id, "tool_result", r, content_type="write_outline")
        # increase_outline_version (simulating snapshot step)
        conv2 = await d.get_conversation(conv.id)
        if conv2 and conv2.current_outline_id:
            await d.increase_outline_version(conv2.current_outline_id)

        # Turn 2: conv_status should see the outline
        cs = make_get_conversation_status(d, conv.id)
        status = await cs.ainvoke({})
        assert status["current_outline_id"] is not None, \
            f"FAIL: current_outline_id is null after write+persist. Full status: {status}"
        assert len(status["outlines"]) >= 1, \
            f"FAIL: outlines is empty after write+persist. Full status: {status}"

    @pytest.mark.asyncio
    async def test_conv_status_sees_outline_no_message_persist(self, db):
        """Simplest case: just write then read, no extra operations."""
        d = Database(db)
        u = await d.create_user("csaw2_user")
        conv = await d.create_conversation(u.id)

        w = make_write_outline_structure(d, conv.id)
        await w.ainvoke({
            "title": "Minimal",
            "sections": [{"section_index": 1, "title": "X", "description": "", "slide_number": 2}],
        })

        cs = make_get_conversation_status(d, conv.id)
        status = await cs.ainvoke({})
        assert status["current_outline_id"] is not None
        assert len(status["outlines"]) >= 1


class TestIdentityMapCache:
    """Simulate chat_send loading conversation before tools run."""

    @pytest.mark.asyncio
    async def test_conv_preload_then_write_then_reread(self, db):
        """chat_send loads conv first → identity map caches current_outline_id=None.
        write_outline_structure sets it → subsequent get_conversation must see the new value."""
        d = Database(db)
        u = await d.create_user("imc_user")
        conv = await d.create_conversation(u.id)

        # Step 1: chat_send loads the conversation (puts it in identity map)
        conv1 = await d.get_conversation(conv.id)
        assert conv1.current_outline_id is None

        # Step 2: write_outline_structure runs, sets current_outline_id
        write_tool = make_write_outline_structure(d, conv.id)
        await write_tool.ainvoke({
            "title": "IMC Test",
            "sections": [{"section_index": 1, "title": "Ch1", "description": "", "slide_number": 2}],
        })

        # Step 3: get_conversation_status must return the NEW current_outline_id
        status_tool = make_get_conversation_status(d, conv.id)
        status = await status_tool.ainvoke({})
        assert status["current_outline_id"] is not None, \
            f"Identity map returned stale null after set_conversation_outline: {status}"
        assert len(status["outlines"]) >= 1, \
            f"Outlines still empty after write_outline: {status}"

        # Step 4: direct get_conversation also must see it
        conv2 = await d.get_conversation(conv.id)
        assert conv2.current_outline_id == status["current_outline_id"], \
            f"get_conversation returned different value: {conv2.current_outline_id} vs {status['current_outline_id']}"


class TestDatabaseConcurrency:
    """Stress-test Database._lock under asyncio.gather (simulating gen_content)."""

    @pytest.mark.asyncio
    async def test_concurrent_reads_same_db(self, db):
        """Multiple coroutines reading from the same Database simultaneously."""
        import asyncio
        d = Database(db)
        u = await d.create_user("conc_r_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Concurrent Read")
        await d.set_conversation_outline(conv.id, o.id)
        for i in range(10):
            await d.create_outline_slide(o.id, i + 1, f"Slide {i}")

        async def read_conv(n):
            for _ in range(10):
                c = await d.get_conversation(conv.id)
                assert c.current_outline_id == o.id

        async def read_outline(n):
            for _ in range(10):
                ol = await d.get_outline(o.id)
                assert ol.title == "Concurrent Read"

        async def read_slides(n):
            for _ in range(10):
                sl = await d.get_slides_by_outline_id(o.id)
                assert len(sl) == 10

        # 5 coroutines × 3 tasks = 15 concurrent, 10 iterations each = 150 DB ops
        tasks = []
        for i in range(5):
            tasks.append(read_conv(i))
            tasks.append(read_outline(i))
            tasks.append(read_slides(i))
        await asyncio.gather(*tasks)

    @pytest.mark.asyncio
    async def test_concurrent_writes_same_db(self, db):
        """Multiple coroutines writing to the same Database simultaneously."""
        import asyncio
        d = Database(db)
        u = await d.create_user("conc_w_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Concurrent Write")
        await d.set_conversation_outline(conv.id, o.id)

        async def create_slides(n):
            for i in range(5):
                await d.create_outline_slide(o.id, n * 100 + i, f"Slide_{n}_{i}")
            return n

        # 5 concurrent writers, 5 slides each = 25 writes
        results = await asyncio.gather(*[create_slides(i) for i in range(5)])
        assert len(results) == 5

        slides = await d.get_slides_by_outline_id(o.id)
        assert len(slides) == 25

    @pytest.mark.asyncio
    async def test_concurrent_read_write_mixed(self, db):
        """Simulate gen_content pattern: reads + writes on same DB concurrently."""
        import asyncio
        d = Database(db)
        u = await d.create_user("conc_mix_user")
        conv = await d.create_conversation(u.id)

        async def write_and_read(n):
            # Write
            o = await d.create_outline(u.id, conv.id, f"Mix_{n}")
            await d.create_outline_slide(o.id, 1, f"Mix_Slide_{n}")
            # Read
            ol = await d.get_outline(o.id)
            sl = await d.get_slides_by_outline_id(o.id)
            return {"title": ol.title, "slides": len(sl)}

        # 8 concurrent mixed read+write
        results = await asyncio.gather(*[write_and_read(i) for i in range(8)])
        assert len(results) == 8
        for r in results:
            assert r["title"].startswith("Mix_")
            assert r["slides"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_with_independent_sessions(self, db):
        """Simulate gen_content: each task gets its own Database instance.

        Uses the same test sessionmaker (not the global singleton which may
        point to a different database under test).
        """
        import asyncio
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from pptgenius.infrastructure.config.settings import get_settings

        # Derive test DB URL from settings (same as conftest)
        prod_url = get_settings().db.url
        test_url = prod_url.rsplit("/", 1)[0] + "/pptgenius_test"
        test_engine = create_async_engine(test_url, echo=False)
        sm = async_sessionmaker(test_engine, expire_on_commit=False)

        d = Database(db)
        u = await d.create_user("conc_ind_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Independent Sessions")
        await d.set_conversation_outline(conv.id, o.id)

        async def do_work(n):
            gdb = Database(sm())
            try:
                for _ in range(3):
                    ol = await gdb.get_outline(o.id)
                    await gdb.create_outline_slide(o.id, n * 100 + _ + 1, f"IS_{n}_{_}")
                sl = await gdb.get_slides_by_outline_id(o.id)
                return {"title": ol.title, "total_slides": len(sl)}
            finally:
                await gdb.db.close()

        # 12 concurrent independent sessions, 3 writes each = 36 writes
        results = await asyncio.gather(*[do_work(i) for i in range(12)])
        assert len(results) == 12

        for r in results:
            assert r["title"] == "Independent Sessions"
            assert r["total_slides"] >= 3

        await test_engine.dispose()


class TestKnowledgeTools:
    """Test the knowledge agent notebook tools (submit_note + read_file)."""

    @pytest.mark.asyncio
    async def test_submit_note_appends(self):
        """submit_note should accumulate notes across multiple calls."""
        from pptgenius.agent.outline.knowledge import _make_submit_note

        tool, notes = _make_submit_note()
        r1 = await tool.ainvoke({"text": "要点1: LangChain是一个LLM框架"})
        r2 = await tool.ainvoke({"text": "要点2: 支持Agent和Tool"})
        assert "已记录 (1条)" in r1
        assert "已记录 (2条)" in r2
        assert len(notes) == 2
        assert notes[0] == "要点1: LangChain是一个LLM框架"

    @pytest.mark.asyncio
    async def test_submit_note_concurrent(self):
        """Multiple concurrent submit_note calls should all be recorded."""
        import asyncio
        from pptgenius.agent.outline.knowledge import _make_submit_note

        tool, notes = _make_submit_note()

        async def write(i):
            await tool.ainvoke({"text": f"note_{i}"})

        await asyncio.gather(*[write(i) for i in range(20)])
        assert len(notes) == 20
        texts = sorted(notes)
        assert texts[0] == "note_0"
        assert texts[-1] == "note_9"

    @pytest.mark.asyncio
    async def test_read_file_tool(self, db):
        """read_file should return file content from DB chunks."""
        from pptgenius.agent.outline.knowledge_tools import make_read_file

        d = Database(db)
        u = await d.create_user("kt_user")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(u.id, "test.txt", "/tmp/kttest.txt", "txt", conversation_id=conv.id)
        await d.create_chunk(kf.id, 0, "chunk zero")
        await d.create_chunk(kf.id, 1, "chunk one")

        count = [0]
        fetched = set()
        tool = make_read_file(d, count, fetched)
        result = await tool.ainvoke({"file_id": kf.id})
        assert "chunk zero" in result
        assert "chunk one" in result
        assert kf.id in fetched
        assert count[0] == 1

    @pytest.mark.asyncio
    async def test_read_file_limit(self, db):
        """read_file should enforce the 5-call limit."""
        from pptgenius.agent.outline.knowledge_tools import make_read_file

        d = Database(db)
        u = await d.create_user("kt2_user")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(u.id, "t.txt", "/tmp/kt2.txt", "txt", conversation_id=conv.id)
        await d.create_chunk(kf.id, 0, "x")

        count = [5]  # already at limit
        fetched = set()
        tool = make_read_file(d, count, fetched)
        result = await tool.ainvoke({"file_id": kf.id})
        assert "已达上限" in result

    @pytest.mark.asyncio
    async def test_knowledge_tools_concurrent(self, db):
        """Concurrent read_file + submit_note should work safely with DB lock."""
        import asyncio
        from pptgenius.agent.outline.knowledge import _make_submit_note
        from pptgenius.agent.outline.knowledge_tools import make_read_file

        d = Database(db)
        u = await d.create_user("ktc_user")
        conv = await d.create_conversation(u.id)

        kf = await d.create_knowledge_file(u.id, "ct.txt", "/tmp/ktc.txt", "txt", conversation_id=conv.id)
        for i in range(10):
            await d.create_chunk(kf.id, i, f"concurrent chunk {i}")

        count = [0]
        fetched = set()
        read_tool = make_read_file(d, count, fetched)
        note_tool, notes = _make_submit_note()

        async def read_and_note(i):
            result = await read_tool.ainvoke({"file_id": kf.id})
            await note_tool.ainvoke({"text": f"from_{i}: {result[:50]}"})

        await asyncio.gather(*[read_and_note(i) for i in range(3)])
        assert len(notes) >= 1
        assert count[0] >= 1


class TestGeneratorPromptKnowledgeFiles:
    """Verify build_generator_user_prompt includes knowledge file IDs."""

    @pytest.mark.asyncio
    async def test_prompt_includes_knowledge_files(self, db):
        from pptgenius.agent.outline.prompts import build_generator_user_prompt

        d = Database(db)
        u = await d.create_user("gpkf_user")
        conv = await d.create_conversation(u.id)
        o = await d.create_outline(u.id, conv.id, "Test Outline")
        sec = await d.create_outline_section(o.id, 1, "Section 1")
        await d.create_outline_slide(o.id, 1, "Slide 1", section_id=sec.id)

        kf = await d.create_knowledge_file(u.id, "doc.pdf", "/tmp/gpkf.pdf", "pdf", conversation_id=conv.id)
        await d.create_chunk(kf.id, 0, "sample content")

        prompt = await build_generator_user_prompt(
            db=d, outline_id=o.id, section_id=sec.id, query="test",
            user_id=u.id, conversation_id=conv.id,
        )
        assert "可用知识文件" in prompt
        assert f"file_id={kf.id}" in prompt
        assert "doc.pdf" in prompt

    @pytest.mark.asyncio
    async def test_prompt_no_orphan_file_ids(self, db):
        """Knowledge files from other conversations should NOT appear."""
        import secrets
        from pptgenius.agent.outline.prompts import build_generator_user_prompt

        d = Database(db)
        u = await d.create_user("gpkf2_user")
        conv_a = await d.create_conversation(u.id)
        conv_b = await d.create_conversation(u.id)

        # Unique paths to avoid dedup collision with other tests
        tag = secrets.token_hex(4)
        kf_a = await d.create_knowledge_file(u.id, "a.pdf", f"/tmp/gpkf_a_{tag}.pdf", "pdf", conversation_id=conv_a.id)
        await d.create_chunk(kf_a.id, 0, "content a")
        kf_b = await d.create_knowledge_file(u.id, "b.pdf", f"/tmp/gpkf_b_{tag}.pdf", "pdf", conversation_id=conv_b.id)
        await d.create_chunk(kf_b.id, 0, "content b")

        o = await d.create_outline(u.id, conv_a.id, "Outline A")
        sec = await d.create_outline_section(o.id, 1, "S1")
        await d.create_outline_slide(o.id, 1, "Slide", section_id=sec.id)

        prompt = await build_generator_user_prompt(
            db=d, outline_id=o.id, section_id=sec.id,
            user_id=u.id, conversation_id=conv_a.id,
        )
        # Only conv_a's file should appear
        assert f"file_id={kf_a.id}" in prompt
        assert f"file_id={kf_b.id}" not in prompt


class TestKnowledgeToolLimits:
    """Verify tool call limits are enforced (search_knowledge ≤9, search_web ≤6, fetch_web ≤4, read_file ≤3)."""

    @pytest.mark.asyncio
    async def test_search_knowledge_limit(self, db):
        from pptgenius.agent.outline.knowledge_tools import make_search_knowledge

        d = Database(db)
        u = await d.create_user("ktl_user")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(u.id, "x.txt", "/tmp/x.txt", "txt", conversation_id=conv.id)
        await d.create_chunk(kf.id, 0, "test content")

        count = [0]
        tool = make_search_knowledge(d, u.id, conv.id, "user", count)

        # 9 calls should succeed
        for i in range(9):
            r = await tool.ainvoke({"query": f"test_{i}"})
            assert "已达上限" not in r

        # 10th call should fail
        r = await tool.ainvoke({"query": "overflow"})
        assert "已达上限" in r

    @pytest.mark.asyncio
    async def test_search_web_limit(self, db):
        from pptgenius.agent.outline.knowledge_tools import make_search_web

        count = [0]
        tool = make_search_web(count)

        for _ in range(6):
            r = await tool.ainvoke({"query": "test"})
            assert "已达上限" not in r

        r = await tool.ainvoke({"query": "overflow"})
        assert "已达上限" in r

    @pytest.mark.asyncio
    async def test_read_file_limit(self, db):
        from pptgenius.agent.outline.knowledge_tools import make_read_file

        d = Database(db)
        u = await d.create_user("ktl2_user")
        conv = await d.create_conversation(u.id)
        kf = await d.create_knowledge_file(u.id, "r.txt", "/tmp/r.txt", "txt", conversation_id=conv.id)
        await d.create_chunk(kf.id, 0, "x")

        count = [0]
        fetched = set()
        tool = make_read_file(d, count, fetched)

        for _ in range(3):
            # Need different file_ids since read_file deduplicates
            kf2 = await d.create_knowledge_file(u.id, f"r{_}.txt", f"/tmp/r{_}.txt", "txt", conversation_id=conv.id)
            await d.create_chunk(kf2.id, 0, f"c{_}")
            r = await tool.ainvoke({"file_id": kf2.id})
            assert "已达上限" not in r

        r = await tool.ainvoke({"file_id": 99999})
        assert "已达上限" in r


# Import tool factories at module level for test discovery
from pptgenius.agent.tools.perception import (
    make_get_conversation_status,
    make_get_knowledge_files,
    make_get_outline,
    make_get_outline_slide,
    make_get_presentation,
    make_search_styles,
    make_switch_outline,
)
from pptgenius.agent.tools.structure import make_modify_outline_structure, make_write_outline_structure
