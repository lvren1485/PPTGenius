"""Structure tools — write_outline_structure, modify_outline_structure.

Auto-inject conversation_id via closure.  All index values are 1-based.
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database


def make_write_outline_structure(db: Database, conversation_id: int) -> Callable:
    """Create outline + sections + auto title_slide & ending_slide + set current_outline_id."""

    async def _write_outline_structure(
        title: str,
        sections: list[dict],
    ) -> str:
        """Create a new outline with sections. title_slide and ending_slide are added automatically."""
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

        # Compute max slide_index from sections content + ending slide
        max_idx = 2  # title(1) + ending placeholder
        await db.create_outline_slide(
            outline_id=outline.id, slide_index=max_idx,
            title="谢谢", layout_type="thanks",
        )

        await db.set_conversation_outline(conversation_id, outline.id)

        return (
            f"已创建大纲:'{title}'(id={outline.id}), "
            f"{len(sections)} sections, title+ending 已自动添加"
        )

    return tool(_write_outline_structure)


def make_modify_outline_structure(db: Database, conversation_id: int) -> Callable:
    """Modify outline: pure DB ops execute directly; content ops create placeholders."""

    async def _modify_outline_structure(operations: list[dict]) -> str:
        """Modify outline structure: rename/delete/reorder are immediate; merge/split/insert create placeholders."""
        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return "错误: 没有选中大纲，请先切换或创建大纲"

        outline_id = conv.current_outline_id
        slides = await db.get_slides_by_outline_id(outline_id)
        slide_map = {sl.slide_index: sl for sl in slides}

        pure_count = {"rename": 0, "delete": 0, "reorder": 0}
        placeholder_count = 0
        notes: list[str] = []

        for op in operations:
            op_type = op.get("op")

            if op_type == "rename_slide":
                si = op["slide_index"]
                sl = slide_map.get(si)
                if sl:
                    await db.update_outline_slide(sl.id, title=op["new_title"])
                    pure_count["rename"] += 1
                else:
                    notes.append(f"rename failed: slide_index={si} not found")

            elif op_type == "delete_slide":
                si = op["slide_index"]
                sl = slide_map.get(si)
                if sl:
                    await db.delete_outline_slide(sl.id)
                    pure_count["delete"] += 1
                else:
                    notes.append(f"delete failed: slide_index={si} not found")

            elif op_type == "reorder_slides":
                section_index = op.get("section_index")
                order = op.get("slide_order", [])
                for new_idx, old_idx in enumerate(order, start=1):
                    sl = slide_map.get(old_idx)
                    if sl:
                        await db.update_outline_slide_index(sl.id, new_idx)
                pure_count["reorder"] += 1

            elif op_type == "merge_slides":
                indices = sorted(op["slide_indices"])
                new_title = op.get("new_title", "合并页")
                # Insert placeholder at the first index position
                await db.insert_outline_slide_after(
                    outline_id=outline_id, after_index=indices[0] - 1,
                    title=new_title, layout_type="content",
                )
                # Mark old slides deleted
                for si in indices:
                    sl = slide_map.get(si)
                    if sl:
                        await db.update_outline_slide_status(sl.id, "deleted")
                placeholder_count += 1

            elif op_type == "split_slide":
                si = op["slide_index"]
                sl = slide_map.get(si)
                if sl:
                    await db.insert_outline_slide_after(
                        outline_id=outline_id, after_index=si,
                        title=f"{sl.title}(拆分)", layout_type=sl.layout_type,
                    )
                    placeholder_count += 1

            elif op_type == "insert_slide":
                after_idx = op["after_slide_index"]
                await db.insert_outline_slide_after(
                    outline_id=outline_id, after_index=after_idx,
                    title=op.get("title", "新页"), layout_type="content",
                )
                placeholder_count += 1

        result_parts = []
        for k in ("rename", "delete", "reorder"):
            if pure_count[k]:
                result_parts.append(f"{k}×{pure_count[k]}")
        if placeholder_count:
            result_parts.append(f"占位×{placeholder_count}")

        result = f"完成: {', '.join(result_parts) if result_parts else '无操作'}"
        if placeholder_count:
            result += "。占位 slide 需调用 outline_section 填充内容"
        if notes:
            result += f"\n注意: {'; '.join(notes)}"

        return result

    return tool(_modify_outline_structure)
