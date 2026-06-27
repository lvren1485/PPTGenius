"""Static tests for decor_check — emoji detection + decor style enforcement."""

import pytest

from pptgenius.agent.ppt.decor_check import has_emoji, check_decor


class TestHasEmoji:
    def test_plain_text(self):
        assert has_emoji("Hello world") is False
        assert has_emoji("你好世界") is False
        assert has_emoji("") is False

    def test_emoji_detected(self):
        assert has_emoji("标题 🍕 很有趣") is True
        assert has_emoji("⭐ 推荐") is True
        assert has_emoji("🎉") is True

    def test_special_chars_not_emoji(self):
        """Normal CJK punctuation should not be flagged as emoji."""
        assert has_emoji("「你好」") is False
        assert has_emoji("——分割线——") is False


# ── helpers ──

def _make_buf(plan=None):
    if plan is None:
        plan = {"parts": {}}
    return {"plan": plan}


def _make_el(el_type="textbox", content_text="Hello", name=None):
    el = {"type": el_type}
    if el_type == "textbox" and content_text:
        el["content"] = [{"paragraph": {"runs": [{"text": content_text}]}}]
    if el_type == "picture" and name:
        el["name"] = name
    return el


def _make_plan(decor_style=None, parts=None):
    p = {"decor_style": decor_style, "parts": parts or {}}
    if decor_style is None:
        del p["decor_style"]
    return p


class TestCheckDecor:
    def test_no_plan(self):
        assert check_decor(_make_el("textbox", "Hello"), {}) == ""

    def test_plain_element_no_conflict(self):
        el = _make_el("textbox", "普通文字")
        result = check_decor(el, _make_buf(_make_plan("icon")))
        assert result == ""

    def test_first_icon_locks_style(self):
        buf = _make_buf(_make_plan())
        el = _make_el("picture", name="star")
        result = check_decor(el, buf)
        assert result == ""
        assert buf["plan"]["decor_style"] == "icon"

    def test_first_emoji_locks_style(self):
        buf = _make_buf(_make_plan())
        el = _make_el("textbox", "标题 🍕")
        result = check_decor(el, buf)
        assert result == ""
        assert buf["plan"]["decor_style"] == "emoji"

    def test_emoji_conflict_with_icon_style(self):
        buf = _make_buf(_make_plan("icon"))
        el = _make_el("textbox", "不要用 🍕")
        result = check_decor(el, buf)
        assert "icon" in result
        assert "emoji" in result

    def test_icon_conflict_with_emoji_style(self):
        buf = _make_buf(_make_plan("emoji"))
        el = _make_el("picture", name="star")
        result = check_decor(el, buf)
        assert "emoji" in result
        assert "icon" in result

    def test_multiple_icons_no_conflict(self):
        buf = _make_buf(_make_plan("icon"))
        assert check_decor(_make_el("picture", name="star"), buf) == ""
        assert check_decor(_make_el("picture", name="cpu"), buf) == ""

    def test_part_level_decor_style(self):
        """decor_style from individual parts should be detected."""
        parts = {"装饰区": {"decor_style": "emoji", "status": "pending"}}
        buf = _make_buf(_make_plan(parts=parts))
        el = _make_el("picture", name="star")
        result = check_decor(el, buf)
        assert "emoji" in result
