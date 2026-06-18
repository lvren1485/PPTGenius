"""Structure tools — create_empty_outline, write_outline_structure, modify_outline_structure, rearrange."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import tool

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.agent.tools.structure")

_STATUS_MERGE = "merge"
_STATUS_SPLIT = "split"
_STATUS_NEW = "new"
_STATUS_MODIFY = "modify"
_PRES_MODIFIED_PREFIX = "o_modified_"

_ID_KEYS = {
    "rename": ["slide_id"],
    "delete": ["target_id", "merge_id"],
    "insert": ["after_id"],
    "move":   ["target_id", "after_id"],
}


def _check_duplicates(operations: list[dict]) -> str | None:
    id_positions: dict[int, list[int]] = {}
    for i, op in enumerate(operations):
        for key in _ID_KEYS.get(op.get("op", ""), []):
            v = op.get(key)
            if v is not None:
                id_positions.setdefault(v, []).append(i)
    duplicates = {k: v for k, v in id_positions.items() if len(v) > 1}
    if not duplicates:
        return None
    lines = ["错误: 以下 slide ID 在多个操作中重复出现，请拆分为多次独立调用:"]
    for sid, positions in sorted(duplicates.items()):
        ops = [f"#{p+1}({operations[p].get('op','?')})" for p in positions]
        lines.append(f"  slide_id={sid} 出现在: {', '.join(ops)}")
    lines.append("建议: 将冲突的操作分批，每批调用一次 modify_outline_structure")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# create_empty_outline — call BEFORE explore
# ═══════════════════════════════════════════════════════════════════

def make_create_empty_outline(db: Database, conversation_id: int) -> Callable:

    async def _create_empty_outline(title: str = "") -> str:
        """Create a new empty outline and set it as the current outline.

        MUST be called BEFORE explore_knowledge.  The outline starts with no
        sections or slides — explore will provide the structure later.

        Args:
            title: Optional initial title (can be empty).
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None:
            return f"错误: 对话 {conversation_id} 不存在"

        outline = await db.create_outline(
            user_id=conv.user_id,
            conversation_id=conversation_id,
            title=title or "未命名大纲",
            slide_count=0,
        )
        await db.set_conversation_outline(conversation_id, outline.id)
        _log.info("empty outline created: id=%d conv=%d", outline.id, conversation_id)
        return f"已创建空白大纲 (id={outline.id})，现在可以调用 explore_knowledge 探索内容。"

    return tool(_create_empty_outline)


# ═══════════════════════════════════════════════════════════════════
# write_outline_structure — write sections + slides to current outline
# ═══════════════════════════════════════════════════════════════════

def make_write_outline_structure(db: Database, conversation_id: int) -> Callable:

    async def _write_outline_structure(
        title: str,
        sections: list[dict],
    ) -> str:
        """Write sections and slides to the CURRENT outline. Replaces old structure.

        This tool modifies the existing outline — does NOT create a new one.  Call
        create_empty_outline first if starting fresh.

        Each section may include citations from explore_knowledge:
        {title, description, slide_number, citations: {file_ids: [...], chunk_ids: [...]}}

        The tool will: (1) soft-delete any old outline slides, (2) create new
        sections with citations stored in DB, (3) pre-create section+content slides.

        Args:
            title: The presentation title (updates existing outline title).
            sections: List of {section_index, title, description, slide_number, citations?}.
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None:
            return f"错误: 对话 {conversation_id} 不存在"
        outline_id = conv.current_outline_id
        if outline_id is None:
            return "错误: 没有选中大纲。请先调用 create_empty_outline。"

        n_sections = len(sections)
        if n_sections == 0:
            return "错误: 至少需要1个章节"

        # ── 1. Soft-delete old outline slides ──
        old_slides = await db.get_slides_by_outline_id(outline_id)
        deleted = 0
        for s in old_slides:
            if s.status != "deleted":
                await db.soft_delete_outline_slide(s.id)
                deleted += 1

        # ── 2. Soft-delete old sections ──
        old_secs = await db.get_sections_by_outline_id(outline_id)
        for s in old_secs:
            await db.soft_delete_outline_section(s.id)

        # ── 3. Update outline title ──
        await db.set_outline_title(outline_id, title)

        # ── 4. Create new sections + slides ──
        total_body = 0
        slide_index = 2  # 0=title, 1=TOC
        for s in sections:
            count = max(s.get("slide_number", 3), 2)
            total_body += count

            citations = s.get("citations", None)

            sec = await db.create_outline_section(
                outline_id=outline_id,
                section_index=s["section_index"],
                title=s["title"],
                description=s.get("description", ""),
                citations=citations,
            )
            # Update slide_count on section
            await db.update_outline_section(sec.id, slide_count=count)

            # First slide: section divider
            await db.create_outline_slide(
                outline_id=outline_id, slide_index=slide_index,
                title=s["title"], layout_type="section",
                section_id=sec.id,
            )
            slide_index += 1

            # Content slides
            for j in range(count - 1):
                await db.create_outline_slide(
                    outline_id=outline_id, slide_index=slide_index,
                    title=f"{s['title']} - {j + 1}", layout_type="content",
                    section_id=sec.id,
                )
                slide_index += 1

        # Title at 0, TOC at 1, ending at 99
        await db.create_outline_slide(outline_id, 0, title, layout_type="title")
        await db.create_outline_slide(outline_id, 1, "目录", layout_type="content")
        await db.create_outline_slide(outline_id, 99, "谢谢", layout_type="thanks")

        total = total_body + 3
        await db.set_outline_slide_count(outline_id, total)

        _log.info("outline written: id=%d title='%s' sections=%d slides=%d (deleted %d old)",
                   outline_id, title, n_sections, total, deleted)
        return (
            f"已写入大纲:'{title}'(id={outline_id}), "
            f"{n_sections} sections, 共 {total} 页 (清理了 {deleted} 个旧 slide)"
        )

    return tool(_write_outline_structure)


# ═══════════════════════════════════════════════════════════════════
# modify_outline_structure
# ═══════════════════════════════════════════════════════════════════

def make_modify_outline_structure(db: Database, conversation_id: int) -> Callable:

    async def _modify_outline_structure(operations: list[dict]) -> dict:
        """Modify the outline structure. All operations use slide IDs, NOT indices.

        Batch pre-check: every slide_id/target_id/after_id/merge_id must be unique.
        Duplicate slide IDs will cause the entire batch to be rejected.
        is_copy and is_change_section are bool flags, default False.

        Operations:
          rename: {op, slide_id, new_title, modify_content?} — rename slide.
                   If modify_content=true, also sets status="modify" for regeneration.
          delete: {op, target_id, merge_id?} — delete target_id. merge_id appends target's
                   content to merge, sets merge status="merge".
          insert: {op, after_id, is_copy?} — insert after after_id. is_copy=true copies
                   content from after_id, sets both status="split". New slide inherits
                   after_id's section_id.
          move:   {op, target_id, after_id, is_change_section?} — move target_id after
                   after_id. Inherits section_id. If section changes, is_change_section
                   must be true or rejected.

        Returns {summary, placeholder_slide_ids} where placeholder_slide_ids lists
        slides that need content regeneration via modify_outline_section.

        Args:
            operations: List of operation dicts, executed in order.
        """
        err = _check_duplicates(operations)
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
                modify_content = op.get("modify_content", False)
                ok = await db.update_outline_slide(
                    sid, title=new_title,
                    status=_STATUS_MODIFY if modify_content else None,
                )
                if ok:
                    rename_count += 1
                    if modify_content:
                        placeholder_ids.append(sid)
                        await _cascade_pres_status(db, sid, _PRES_MODIFIED_PREFIX + _STATUS_MODIFY)
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
                    await db.update_outline_slide(merge_id, status=_STATUS_MERGE)
                    placeholder_ids.append(merge_id)
                    await _cascade_pres_status(db, merge_id, _PRES_MODIFIED_PREFIX + _STATUS_MERGE)
                await db.soft_delete_outline_slide(target_id)
                await _cascade_pres_status(db, target_id, _PRES_MODIFIED_PREFIX + "deleted")

            elif op_type == "insert":
                after_id, is_copy = op["after_id"], op.get("is_copy", False)
                after = await db.get_outline_slide(after_id)
                if after is None:
                    notes.append(f"insert 失败: after_id={after_id} 不存在")
                    continue
                new_title = after.title or "新页"
                content = None
                new_status = _STATUS_NEW
                if is_copy:
                    await db.update_outline_slide(after_id, status=_STATUS_SPLIT)
                    new_title = after.title or "新页"
                    content = dict(after.content_json) if after.content_json else None
                    placeholder_ids.append(after_id)
                    await _cascade_pres_status(db, after_id, _PRES_MODIFIED_PREFIX + _STATUS_SPLIT)
                    new_status = _STATUS_SPLIT
                new_slide = await db.insert_outline_slide_after(
                    outline_id=outline_id, after_slide_id=after_id,
                    title=new_title, section_id=after.section_id,
                    content_json=content, notes=None,
                )
                await db.update_outline_slide_status(new_slide.id, new_status)
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
                all_slides = await db.get_slides_by_outline_id(outline_id)
                tgt_idx = target.slide_index
                aft_idx = after.slide_index
                if tgt_idx < aft_idx:
                    for s in all_slides:
                        if tgt_idx < s.slide_index <= aft_idx:
                            await db.update_outline_slide_index(s.id, s.slide_index - 1)
                    await db.update_outline_slide_index(target_id, aft_idx)
                elif tgt_idx > aft_idx:
                    for s in all_slides:
                        if aft_idx < s.slide_index < tgt_idx:
                            await db.update_outline_slide_index(s.id, s.slide_index + 1)
                    await db.update_outline_slide_index(target_id, aft_idx + 1)
                await db.update_outline_slide(target_id, section_id=after.section_id)

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

        _log.info("modify outline=%d: %s", outline_id, summary)
        return {"summary": summary, "placeholder_slide_ids": placeholder_ids}

    return tool(_modify_outline_structure)


# ═══════════════════════════════════════════════════════════════════
# rearrange_presentation_slides
# ═══════════════════════════════════════════════════════════════════

def make_rearrange_presentation_slides(db: Database, conversation_id: int) -> Callable:

    async def _rearrange_presentation_slides() -> str:
        """Sync presentation_slides with outline_slides.

        - o_modified_deleted → soft-delete the pres slide
        - Other o_modified_* → keep status (content agent reads it via prompt)
        - Creates missing pres slides for new outline slides
        - Overwrites all pres slide_index from outline slides
        """
        conv = await db.get_conversation(conversation_id)
        if conv is None or conv.current_outline_id is None:
            return "错误：没有选中大纲"

        outline_id = conv.current_outline_id
        pres_list = await db.list_presentations_by_conversation(conversation_id)
        pres = next((p for p in pres_list
                     if p.outline_id == outline_id and p.status != "deleted"), None)
        if pres is None:
            return "错误：当前大纲没有关联的 presentation"

        from sqlalchemy import select as _sel
        from pptgenius.infrastructure.db.models import PresentationSlide

        result = await db.db.execute(
            _sel(PresentationSlide)
            .where(PresentationSlide.presentation_id == pres.id)
            .where(PresentationSlide.status.like(_PRES_MODIFIED_PREFIX + "%"))
        )
        modified = list(result.scalars().all())

        deleted = 0
        for ps in modified:
            st = ps.status or ""
            if st.endswith("_deleted"):
                await db.soft_delete_presentation_slide(ps.id)
                deleted += 1
        if deleted:
            await db.db.commit()

        outline_slides = await db.get_slides_by_outline_id(outline_id)
        all_pres = await db.get_slides_by_presentation_id(pres.id)
        pres_by_outline = {s.outline_slide_id: s for s in all_pres if s.outline_slide_id}

        created = 0
        for idx, oslide in enumerate(outline_slides, start=1):
            ps = pres_by_outline.get(oslide.id)
            if ps is None:
                await db.create_presentation_slide(
                    presentation_id=pres.id,
                    slide_index=idx,
                    layout_name=oslide.layout_type or "content",
                    outline_slide_id=oslide.id,
                    style_id=pres.style_id,
                )
                created += 1
            else:
                ps.slide_index = idx
        if created:
            await db.db.commit()

        pres.version = 0
        return f"重排完成: 删除 {deleted}, 新建 {created}"

    return tool(_rearrange_presentation_slides)


# ═══════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════

async def _cascade_pres_status(db: Database, outline_slide_id: int, status: str) -> None:
    from sqlalchemy import update as _up
    from pptgenius.infrastructure.db.models import PresentationSlide
    await db.db.execute(
        _up(PresentationSlide)
        .where(PresentationSlide.outline_slide_id == outline_slide_id)
        .values(status=status[:20])
    )


def _find(slides: list, slide_id: int):
    for s in slides:
        if s.id == slide_id:
            return s
    return None


def _merge_into(target, into) -> None:
    tc = target.content_json or {}
    ic = into.content_json or {}
    if not ic:
        ic = {"main_points": [], "detailed_content": ""}
    ic.setdefault("main_points", [])
    ic["main_points"].extend(tc.get("main_points", []))
    if tc.get("detailed_content"):
        ic["detailed_content"] = ic.get("detailed_content", "") + "\n---\n" + tc["detailed_content"]
    into.content_json = ic
