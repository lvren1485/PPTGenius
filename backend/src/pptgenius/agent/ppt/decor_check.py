"""Decorative element consistency — emoji vs icon mutual exclusion.

Unified entry: ``check_decor(element, buffer) → str`` — returns error string
if decor conflict detected, empty string otherwise.
"""

from __future__ import annotations

import re

# Common emoji Unicode ranges
_EMOJI_RE = re.compile(
    "[" +
    "\U0001F300-\U0001F9FF"   # Misc Symbols, Emoticons
    "\U0001FA00-\U0001FA6F"   # Chess, symbols
    "\U0001FA70-\U0001FAFF"   # More symbols
    u"☀-➿"          # Misc symbols (☀-➿)
    u"✂-➰"          # ✂-➰
    u"©®"           # © ®
    u"™ℹ"           # ™ ℹ
    u"⌨"                 # ⌨
    u"⏏"                 # ⏏
    u"⏩-⏳"          # ⏩-⏳
    u"⏸-⏺"          # ⏸-⏺
    u"Ⓜ"                 # Ⓜ
    u"▪-▫"          # ▪ ▫
    u"▶◀"           # ▶ ◀
    u"◻-◾"          # ◻-◾
    u"⤴⤵"           # ↩ ↪
    u"〰〽"           # 〰 〽
    u"㊗㊙"           # ㊗ ㊙
    "\U0001F000-\U0001F02F"   # Mahjong, Domino
    "\U0001F0A0-\U0001F0FF"   # Playing cards
    "\U0001F100-\U0001F1FF"   # Enclosed
    "\U0001F200-\U0001F2FF"   # Enclosed ideographic
    "\U0001F600-\U0001F64F"   # Emoticons
    "\U0001F680-\U0001F6FF"   # Transport
    "\U0001F700-\U0001F77F"   # Alchemical
    "\U0001F780-\U0001F7FF"   # Geometric shapes
    "\U0001F800-\U0001F8FF"   # Supplemental Arrows
    "\U0001F900-\U0001F9FF"   # Supplemental Symbols
    "\U0001FA00-\U0001FA6F"   # Chess
    "\U0001FA70-\U0001FAFF"   # Symbols extended
    "\U0001FB00-\U0001FBFF"   # Legacy computing
    "]+"
)


def has_emoji(text: str) -> bool:
    """True if text contains Unicode emoji characters."""
    return bool(_EMOJI_RE.search(text))


def check_decor(element: dict, buffer: dict) -> str:
    """Enforce emoji vs icon consistency. Returns error string or empty.

    When the first decorative element (emoji in text, or icon via picture)
    is submitted, locks in ``decor_style`` on the plan.  Subsequent
    submissions of the opposite type are rejected with a clear error.
    """
    plan = buffer.get("plan")
    if not plan:
        return ""

    # Determine current decor style from plan
    decor_style = plan.get("decor_style")
    if not decor_style:
        for info in plan.get("parts", {}).values():
            ds = info.get("decor_style")
            if ds:
                decor_style = ds
                break

    el_type = element.get("type", "")
    is_icon = (el_type == "picture" and bool(element.get("name")))
    has_emoji_text = False

    if el_type == "textbox":
        for block in element.get("content", []):
            for run in block.get("paragraph", {}).get("runs", []):
                if has_emoji(run.get("text", "")):
                    has_emoji_text = True
                    break

    if not is_icon and not has_emoji_text:
        return ""  # not decorative

    # First decorative submission — lock in the style
    if not decor_style:
        ds = "icon" if is_icon else "emoji"
        plan["decor_style"] = ds
        return ""

    # Conflict check
    if decor_style == "icon" and has_emoji_text:
        return "错误: 本 slide 使用 icon 装饰风格，文本中不应出现 emoji。请删除 emoji 或改用 search_icons。"
    if decor_style == "emoji" and is_icon:
        return "错误: 本 slide 使用 emoji 装饰风格，不应添加 icon。请删除 icon 元素。"

    return ""
