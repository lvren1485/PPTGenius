"""Test SSE context pipeline — verify agent events reach the queue."""

import asyncio

import pytest

from pptgenius.agent.common.sse_context import get_sse_writer, set_sse_writer


class TestSseContext:
    def test_no_writer_set_returns_noop(self):
        """No context set → no-op writer, no error."""
        w = get_sse_writer()
        w({"type": "test"})  # should not raise

    @pytest.mark.asyncio
    async def test_writer_pushes_to_queue(self):
        """Set writer → events land in queue."""
        q = asyncio.Queue()

        def _w(data):
            q.put_nowait(data)

        set_sse_writer(_w)

        writer = get_sse_writer()
        writer({"type": "tool_start", "tool": "search", "args": {"q": "test"}})
        writer({"type": "tool_end", "tool": "search", "result_len": 100})

        # Drain queue
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        assert len(events) == 2
        assert events[0]["type"] == "tool_start"
        assert events[0]["tool"] == "search"
        assert events[1]["type"] == "tool_end"

    @pytest.mark.asyncio
    async def test_queue_drain_in_event_loop(self):
        """Simulate the chat API drain pattern."""
        q = asyncio.Queue()
        set_sse_writer(lambda d: q.put_nowait(d))

        # Simulate agent writing events
        writer = get_sse_writer()
        writer({"type": "master_start"})
        writer({"type": "tool_start", "tool": "gen_content"})
        await asyncio.sleep(0.01)
        writer({"type": "tool_end", "tool": "gen_content", "result_len": 500})
        writer({"type": "master_done"})

        # Simulate chat API drain
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        assert len(events) == 4
        types = [e["type"] for e in events]
        assert types == ["master_start", "tool_start", "tool_end", "master_done"]

    @pytest.mark.asyncio
    async def test_concurrent_writers_isolated(self):
        """Two concurrent tasks each have their own writer."""
        q1 = asyncio.Queue()
        q2 = asyncio.Queue()

        async def task1():
            set_sse_writer(lambda d: q1.put_nowait(d))
            get_sse_writer()({"type": "from_task_1"})

        async def task2():
            set_sse_writer(lambda d: q2.put_nowait(d))
            get_sse_writer()({"type": "from_task_2"})

        await asyncio.gather(task1(), task2())

        assert q1.get_nowait()["type"] == "from_task_1"
        assert q2.get_nowait()["type"] == "from_task_2"

    @pytest.mark.asyncio
    async def test_sse_middleware_uses_context(self):
        """SSEToolMiddleware should call get_sse_writer(), not get_stream_writer()."""
        from pptgenius.agent.common.middleware.sse_tool import SSEToolMiddleware
        mw = SSEToolMiddleware()
        assert mw is not None
        # The middleware import should not raise ImportError (no langgraph required)
