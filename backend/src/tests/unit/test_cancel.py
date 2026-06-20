"""Tests for cancel logic — CancelRegistry."""

import asyncio

import pytest

from pptgenius.api.chat import CancelRegistry


class TestCancelRegistry:
    @pytest.mark.asyncio
    async def test_register_and_cancel(self):
        async def _pending():
            await asyncio.sleep(600)
        t = asyncio.create_task(_pending())
        CancelRegistry.register(42, t)
        assert not t.done()
        CancelRegistry.cancel(42)
        await asyncio.sleep(0.01)
        assert t.cancelled()
        CancelRegistry.unregister(42)

    def test_cancel_nonexistent(self):
        CancelRegistry.cancel(99999)
        CancelRegistry.unregister(99999)

    @pytest.mark.asyncio
    async def test_unregister_cleans(self):
        t = asyncio.create_task(asyncio.sleep(1))
        CancelRegistry.register(1, t)
        CancelRegistry.unregister(1)
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        CancelRegistry.unregister(1)
