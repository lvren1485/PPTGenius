"""Structure tools — write_outline_structure, modify_outline_structure.

Auto-inject conversation_id via closure.  All operations use slide IDs (not indices).
"""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database

from ..common.tool_sse_wrapper import wrap_tool_with_sse

_TAG_MERGE = "（待合并）"
_TAG_SPLIT = "（待分割）"

# keys that reference slide IDs in each operation type
_ID_KEYS = {
    "rename": ["slide_id"],
    "delete": ["target_id", "merge_id"],
    "insert": ["after_id"],
    "move":   ["target_id", "after_id"],
}


def _extract_slide_ids(operations: list[dict]) -> list[int]:
    ids: list[int] = []
    for op in operations:
        for key in _ID_KEYS.get(op.get("op", ""), []):
            v = op.get(key)
            if v is not None:
                ids.append(v)
    return ids


def _check_duplicates(ids: list[int]) -> str | None:
    seen = set()
    dup = set()
    for i in ids:
        if i in seen:
            dup.add(i)
        seen.add(i)
    if dup:
        return f"错误: 以下 slide ID 重复出现: {sorted(dup)}"
    return None


def make_write_outline_structure(db: Database, conversation_id: int) -> Callable:

    async def _write_outline_structure(
        title: str,
        sections: list[dict],
    ) -> str:
        """Create a new outline skeleton with sections, auto-adding title/TOC/ending slides.

        The title_slide (index 1), TOC slide (index 2), and ending_slide (last index)
        are created automatically. Do NOT include them in the sections list.

        Args:
            title: The presentation title.
            sections: List of {section_index, title, description}. section_index starts at 1.
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None:
            return f"错误: 对话 {conversation_id} 不存在"

        outline = await db.create_outline(
            user_id=conv.user_id,
            conversation_id=conversation_id,
            title=title,
        )

        for s in sections:
            await db.create_outline_section(
                outline_id=outline.id,
                section_index=s["section_index"],
                title=s["title"],
                description=s.get("description", ""),
            )

        await db.create_outline_slide(outline.id, 1, title, layout_type="title")
        await db.create_outline_slide(outline.id, 2, "目录", layout_type="content")
        await db.create_outline_slide(outline.id, 3, "谢谢", layout_type="thanks")

        await db.set_conversation_outline(conversation_id, outline.id)
        return (
            f"已创建大纲:'{title}'(id={outline.id}), "
            f"{len(sections)} sections, title+TOC+ending 已自动添加"
        )

    return tool(wrap_tool_with_sse(_write_outline_structure))


def make_modify_outline_structure(db: Database, conversation_id: int) -> Callable:

    async def _modify_outline_structure(operations: list[dict]) -> dict:
        """Modify the outline structure. All operations use slide IDs, NOT indices.

        Batch pre-check: every slide_id/target_id/after_id/merge_id must be unique.
        Duplicate slide IDs will cause the entire batch to be rejected.
        is_copy and is_change_section are bool flags, default False. 

        Operations:
          rename: {op, slide_id, new_title}
          delete: {op, target_id, merge_id?} — delete target_id. merge_id appends target's
                   content to merge, tags merge title "待合并".
          insert: {op, after_id, is_copy?} — insert after after_id. is_copy=true copies
                   content from after_id (split), tags both "待分割". New slide inherits
                   after_id's section_id.
          move:   {op, target_id, after_id, is_change_section?} — move target_id after
                   after_id. Inherits section_id. If section changes, is_change_section
                   must be true or rejected.

        Returns {summary, placeholder_slide_ids} where placeholder_slide_ids lists
        slides that need content regeneration via modify_outline_section.

        Args:
            operations: List of operation dicts, executed in order.
        """
        # ── pre-validation: duplicate slide IDs ──
        err = _check_duplicates(_extract_slide_ids(operations))
        if err:
            return {"error": err}

        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return {"error": "没有选中大纲"}

        outline_id = conv.current_outline_id
        rename_count = 0
        placeholder_ids: list[int] = []
        notes: list[str] = []

        for op in operations:
            op_type = op.get("op")

            if op_type == "rename":
                sid, new_title = op["slide_id"], op["new_title"]
                ok = await db.update_outline_slide(sid, title=new_title)
                if ok:
                    rename_count += 1
                else:
                    notes.append(f"rename 失败: slide {sid} 不存在")

            elif op_type == "delete":
                target_id, merge_id = op["target_id"], op.get("merge_id")
                target = await db.get_outline_slide(target_id)
                if target is None:
                    notes.append(f"delete 失败: target_id={target_id} 不存在")
                    continue
                if merge_id is not None:
                    merge = await db.get_outline_slide(merge_id)
                    if merge is None:
                        notes.append(f"delete 失败: merge_id={merge_id} 不存在")
                        continue
                    _merge_into(target, merge)
                    old_title = merge.title or ""
                    if _TAG_MERGE not in old_title:
                        await db.update_outline_slide(merge_id, title=old_title + _TAG_MERGE)
                    placeholder_ids.append(merge_id)
                await db.delete_outline_slide(target_id)

            elif op_type == "insert":
                after_id, is_copy = op["after_id"], op.get("is_copy", False)
                after = await db.get_outline_slide(after_id)
                if after is None:
                    notes.append(f"insert 失败: after_id={after_id} 不存在")
                    continue
                new_title = "新页"
                content = None
                if is_copy:
                    old_title = after.title or ""
                    if _TAG_SPLIT not in old_title:
                        await db.update_outline_slide(after_id, title=old_title + _TAG_SPLIT)
                    new_title = (after.title or "新页").rstrip(_TAG_SPLIT) + _TAG_SPLIT
                    content = dict(after.content_json) if after.content_json else None
                    placeholder_ids.append(after_id)
                new_slide = await db.insert_outline_slide_after(
                    outline_id=outline_id, after_slide_id=after_id,
                    title=new_title, section_id=after.section_id,
                    content_json=content,
                )
                placeholder_ids.append(new_slide.id)

            elif op_type == "move":
                target_id, after_id = op["target_id"], op["after_id"]
                is_change_section = op.get("is_change_section", False)
                target = await db.get_outline_slide(target_id)
                after = await db.get_outline_slide(after_id)
                if target is None or after is None:
                    notes.append(f"move 失败: slide 不存在")
                    continue
                if target.section_id != after.section_id and not is_change_section:
                    notes.append(
                        f"move: slide {target_id} 跨 section→{after.section_id}, "
                        f"需设置 is_change_section=true"
                    )
                    continue
                # Reindex: shift slides between target and after
                all_slides = await db.get_slides_by_outline_id(outline_id)
                tgt_idx = target.slide_index
                aft_idx = after.slide_index
                if tgt_idx < aft_idx:
                    # target is before after: shift slides (tgt+1 .. aft) down by 1
                    for s in all_slides:
                        if tgt_idx < s.slide_index <= aft_idx:
                            await db.update_outline_slide_index(s.id, s.slide_index - 1)
                    # target now goes at aft_idx
                    await db.update_outline_slide_index(target_id, aft_idx)
                elif tgt_idx > aft_idx:
                    # target is after after: shift slides (aft+1 .. tgt-1) up by 1
                    for s in all_slides:
                        if aft_idx < s.slide_index < tgt_idx:
                            await db.update_outline_slide_index(s.id, s.slide_index + 1)
                    # target now goes after after
                    await db.update_outline_slide_index(target_id, aft_idx + 1)
                # else tgt_idx == aft_idx: no-op (shouldn't happen with unique check)
                await db.update_outline_slide(target_id, section_id=after.section_id)

        # ── result ──
        parts = []
        if rename_count:
            parts.append(f"rename×{rename_count}")
        if placeholder_ids:
            parts.append(f"占位×{len(placeholder_ids)}")
        summary = f"完成: {', '.join(parts) if parts else '无操作'}"
        if placeholder_ids:
            summary += f"。需要生成内容的 slide ID: {placeholder_ids}"
        if notes:
            summary += f"\n注意: {'; '.join(notes)}"

        return {"summary": summary, "placeholder_slide_ids": placeholder_ids}

    return tool(wrap_tool_with_sse(_modify_outline_structure))


# ── helpers ──────────────────────────────────────────────────────────────────

def _find(slides: list, slide_id: int):
    for s in slides:
        if s.id == slide_id:
            return s
    return None


def _merge_into(target, into) -> None:
    """Copy target's content_json into 'into'. Both are ORM objects mutated in-place."""
    tc = target.content_json or {}
    ic = into.content_json or {}
    if not ic:
        ic = {"main_points": [], "detailed_content": ""}
    ic.setdefault("main_points", [])
    ic["main_points"].extend(tc.get("main_points", []))
    if tc.get("detailed_content"):
        ic["detailed_content"] = ic.get("detailed_content", "") + "\n---\n" + tc["detailed_content"]
    into.content_json = ic
