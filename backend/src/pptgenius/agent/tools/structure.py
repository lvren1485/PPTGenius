"""Structure tools — write_outline_structure, modify_outline_structure.

Auto-inject conversation_id via closure.  All index values are 1-based.
"""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database

from ..common.tool_sse_wrapper import wrap_tool_with_sse


def make_write_outline_structure(db: Database, conversation_id: int) -> Callable:
    """Create outline + sections + auto title_slide, TOC, ending_slide + set current_outline_id."""

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

        # Auto-insert title_slide at index 1
        await db.create_outline_slide(
            outline_id=outline.id, slide_index=1,
            title=title, layout_type="title",
        )
        # Auto-insert TOC slide at index 2
        await db.create_outline_slide(
            outline_id=outline.id, slide_index=2,
            title="目录", layout_type="content",
        )
        # Ending slide at last index
        await db.create_outline_slide(
            outline_id=outline.id, slide_index=3,
            title="谢谢", layout_type="thanks",
        )

        await db.set_conversation_outline(conversation_id, outline.id)

        return (
            f"已创建大纲:'{title}'(id={outline.id}), "
            f"{len(sections)} sections, title+TOC+ending 已自动添加"
        )

    return tool(wrap_tool_with_sse(_write_outline_structure))


def make_modify_outline_structure(db: Database, conversation_id: int) -> Callable:
    """Modify outline: pure DB ops execute directly; content ops create placeholders."""

    async def _modify_outline_structure(operations: list[dict]) -> str:
        """Modify the outline structure with one or more operations.

        Pure DB ops execute immediately:
        - rename_slide: {op, slide_index, new_title}
        - delete_slide: {op, slide_index}
        - reorder_slides: {op, slide_order: [new_index_order...]}

        Content ops create placeholder slides, copying content to preserve context,
        requiring a subsequent modify_outline_section call:
        - merge_slides: {op, slide_indices: [idx, ...], new_title}
        - split_slide: {op, slide_index}
        - insert_slide: {op, after_slide_index, title}

        Args:
            operations: List of operation dicts. Order matters — deletions before
                insertions to avoid index conflicts.
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return "错误: 没有选中大纲，请先切换或创建大纲"

        outline_id = conv.current_outline_id
        slides = await db.get_slides_by_outline_id(outline_id)
        # Build slide lookup: we need both by-index and by-id since indexes shift
        slide_by_id = {sl.id: sl for sl in slides}

        pure_count = {"rename": 0, "delete": 0, "reorder": 0}
        placeholder_count = 0
        notes: list[str] = []

        for op in operations:
            op_type = op.get("op")

            if op_type == "rename_slide":
                si = op["slide_index"]
                sl = _find_by_index(slides, si)
                if sl:
                    await db.update_outline_slide(sl.id, title=op["new_title"])
                    pure_count["rename"] += 1
                else:
                    notes.append(f"rename failed: slide_index={si} not found")

            elif op_type == "delete_slide":
                si = op["slide_index"]
                sl = _find_by_index(slides, si)
                if sl:
                    await db.delete_outline_slide(sl.id)
                    pure_count["delete"] += 1
                    # Refresh slide list since delete reindexes
                    slides = await db.get_slides_by_outline_id(outline_id)
                    slide_by_id = {sl.id: sl for sl in slides}
                else:
                    notes.append(f"delete failed: slide_index={si} not found")

            elif op_type == "reorder_slides":
                order = op.get("slide_order", [])
                # Slide_order lists all current slide_index values in desired new order.
                # After reorder, slide 1→new index 1, slide N→new index N.
                slides = await db.get_slides_by_outline_id(outline_id)
                old_to_new = {}
                for new_idx, old_idx in enumerate(order, start=1):
                    sl = _find_by_index(slides, old_idx)
                    if sl:
                        old_to_new[sl.id] = new_idx
                for sid, new_idx in old_to_new.items():
                    await db.update_outline_slide_index(sid, new_idx)
                slides = await db.get_slides_by_outline_id(outline_id)
                slide_by_id = {sl.id: sl for sl in slides}
                pure_count["reorder"] += 1

            elif op_type == "merge_slides":
                indices = sorted(op["slide_indices"])
                new_title = op.get("new_title", "合并页")
                # Collect content from merged slides
                merged_content = _collect_content(slides, indices)
                # Use proper delete (triggers reindex)
                first_si = indices[0]
                for si in reversed(indices):
                    sl = _find_by_index(slides, si)
                    if sl:
                        await db.delete_outline_slide(sl.id)
                slides = await db.get_slides_by_outline_id(outline_id)
                # Insert placeholder with merged content
                await db.insert_outline_slide_after(
                    outline_id=outline_id, after_index=first_si - 1,
                    title=new_title, layout_type="content",
                    content_json=merged_content,
                )
                placeholder_count += 1
                slides = await db.get_slides_by_outline_id(outline_id)
                slide_by_id = {sl.id: sl for sl in slides}

            elif op_type == "split_slide":
                si = op["slide_index"]
                sl = _find_by_index(slides, si)
                if sl:
                    # Copy original content to both new slides as baseline
                    await db.insert_outline_slide_after(
                        outline_id=outline_id, after_index=si,
                        title=f"{sl.title}(拆分A)", layout_type=sl.layout_type,
                        content_json=_copy_content(sl.content_json),
                    )
                    # Update the original (now shifted) to be the B part
                    slides = await db.get_slides_by_outline_id(outline_id)
                    orig = _find_by_index(slides, si)
                    if orig:
                        await db.update_outline_slide(
                            orig.id,
                            title=f"{sl.title}(拆分B)",
                            content_json=_copy_content(sl.content_json),
                        )
                    placeholder_count += 2
                    slides = await db.get_slides_by_outline_id(outline_id)
                    slide_by_id = {sl.id: sl for sl in slides}

            elif op_type == "insert_slide":
                after_idx = op["after_slide_index"]
                await db.insert_outline_slide_after(
                    outline_id=outline_id, after_index=after_idx,
                    title=op.get("title", "新页"), layout_type="content",
                )
                placeholder_count += 1
                slides = await db.get_slides_by_outline_id(outline_id)
                slide_by_id = {sl.id: sl for sl in slides}

        result_parts = []
        for k in ("rename", "delete", "reorder"):
            if pure_count[k]:
                result_parts.append(f"{k}×{pure_count[k]}")
        if placeholder_count:
            result_parts.append(f"占位×{placeholder_count}")

        result = f"完成: {', '.join(result_parts) if result_parts else '无操作'}"
        if placeholder_count:
            result += "。占位 slide 需调用 modify_outline_section 填充内容"
        if notes:
            result += f"\n注意: {'; '.join(notes)}"

        return result

    return tool(wrap_tool_with_sse(_modify_outline_structure))


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_by_index(slides: list, index: int):
    for sl in slides:
        if sl.slide_index == index:
            return sl
    return None


def _collect_content(slides: list, indices: list[int]) -> dict | None:
    """Merge main_points and detailed_content from multiple slides."""
    all_points = []
    all_detail = []
    for si in indices:
        sl = _find_by_index(slides, si)
        if sl and sl.content_json:
            all_points.extend(sl.content_json.get("main_points", []))
            d = sl.content_json.get("detailed_content", "")
            if d:
                all_detail.append(d)
    if not all_points and not all_detail:
        return None
    return {
        "main_points": all_points,
        "detailed_content": "\n---\n".join(all_detail) if all_detail else "",
    }


def _copy_content(content_json: dict | None) -> dict | None:
    """Shallow copy content_json, preserving original structure."""
    if content_json is None:
        return None
    return dict(content_json)
