"""Export Service — singlton that rebuilds PPT / markdown from snapshots."""

from __future__ import annotations

import os
import time
from pathlib import Path

from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.utils import get_logger

_log = get_logger("pptgenius.export")


class ExportService:
    """Export outline (markdown) or presentation (pptx) from snapshots."""

    _instance: "ExportService | None" = None
    _TTL_SECONDS = 86_400  # 1 day

    def __new__(cls) -> "ExportService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_init"):
            return
        self._init = True

    # ── public API ──────────────────────────────────────────────────────

    async def export_outline_md(
        self, db: Database, snapshot_id: int,
    ) -> tuple[str, Path]:
        """Build a markdown file from an outline snapshot.

        Returns (filename, full_path).
        """
        snap = await db.get_outline_snapshot(snapshot_id)
        if snap is None:
            raise FileNotFoundError(f"outline snapshot {snapshot_id} not found")

        outline = snap.outline_json or {}

        # Build file info lookup from citations
        file_map: dict[int, dict] = {}
        for sec in outline.get("sections", []):
            for sl in sec.get("slides", []):
                for c in (sl.get("citations") or []):
                    fid = c.get("knowledge_file_id")
                    if fid and fid not in file_map:
                        kf = await db.get_knowledge_file(fid)
                        if kf:
                            file_map[fid] = {
                                "filename": kf.filename,
                                "source_type": kf.source_type or "",
                                "web_url": kf.web_url or "",
                            }

        md = self._build_outline_markdown(outline, file_map)

        conv_id = snap.conversation_id
        out_dir = self._ensure_output_dir(conv_id)
        filename = f"outline_v{snap.version}_{snapshot_id}.md"
        path = out_dir / filename
        path.write_text(md, encoding="utf-8")
        self._cleanup_old(out_dir)
        return filename, path

    async def export_presentation_pptx(
        self, db: Database, snapshot_id: int,
    ) -> tuple[str, Path]:
        """Build a .pptx file from a presentation snapshot.

        Returns (filename, full_path).
        """
        snap = await db.get_snapshot(snapshot_id)
        if snap is None:
            raise FileNotFoundError(f"presentation snapshot {snapshot_id} not found")

        pres_json = snap.presentation_json or {}
        instruction = self._rebuild_instruction(pres_json)

        conv_id = snap.conversation_id
        out_dir = self._ensure_output_dir(conv_id)
        filename = f"pres_v{snap.version}_{snapshot_id}.pptx"
        path = out_dir / filename

        # Temp workspace for icon generation
        ws = str(out_dir)

        from pptgenius.infrastructure.ppt_engine.generator import generate_ppt
        result = await generate_ppt(instruction, str(path), workspace_path=ws)

        # Clean up old exports
        self._cleanup_old(out_dir)

        if not result["ok"]:
            raise RuntimeError(f"PPT generation failed: {result.get('errors', [])}")
        return filename, path

    # ── internal ─────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_output_dir(conv_id: int) -> Path:
        cfg = get_settings().workspace
        d = Path(cfg.root) / str(conv_id) / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def _cleanup_old(cls, directory: Path) -> None:
        """Delete export files older than TTL."""
        now = time.time()
        for f in directory.glob("*"):
            if f.is_file() and now - f.stat().st_mtime > cls._TTL_SECONDS:
                try:
                    f.unlink()
                    _log.debug("cleaned up old export: %s", f.name)
                except OSError:
                    pass

    @staticmethod
    def _build_outline_markdown(outline: dict, file_map: dict | None = None) -> str:
        if file_map is None:
            file_map = {}
        lines = [f"# {outline.get('title', '未命名')}", ""]
        lines.append(f"版本: {outline.get('version', '?')}")
        lines.append(f"页数: {outline.get('slide_count', 0)}")
        if outline.get("eval_score"):
            lines.append(f"评分: {outline['eval_score']}")
        lines.append("")

        for sec in outline.get("sections", []):
            lines.append(f"## {sec.get('section_index', '?')}. {sec.get('title', '')}")
            if sec.get("description"):
                lines.append(f"> {sec['description']}")
            lines.append("")
            for sl in sec.get("slides", []):
                idx = sl.get("slide_index", "?")
                title = sl.get("title", "")
                lt = sl.get("layout_type", "")
                lines.append(f"### {idx}. {title}")
                if lt:
                    lines.append(f"*layout: {lt}*  ")
                cj = sl.get("content_json", {})
                if isinstance(cj, dict):
                    if cj.get("main_points"):
                        lines.append("")
                        lines.append("**要点:**")
                        for mp in cj["main_points"]:
                            lines.append(f"- {mp}")
                    if cj.get("detailed_content"):
                        lines.append("")
                        lines.append(f"**内容:** {cj['detailed_content'][:500]}")
                    if cj.get("key_data"):
                        lines.append("")
                        lines.append(f"**数据:** {cj['key_data']}")
                    if cj.get("visual_note"):
                        lines.append("")
                        lines.append(f"**视觉:** {cj['visual_note']}")
                if sl.get("notes"):
                    lines.append("")
                    lines.append(f"*备注: {sl['notes'][:200]}*")
                # Citations
                citations = sl.get("citations")
                if citations and isinstance(citations, list) and len(citations) > 0:
                    lines.append("")
                    lines.append("**参考来源:**")
                    for i, c in enumerate(citations, 1):
                        reason = c.get("reason", "") or ""
                        fid = c.get("knowledge_file_id", "?")
                        finfo = file_map.get(fid, {})
                        fname = finfo.get("filename", f"file_id={fid}")
                        if finfo.get("source_type") == "web" and finfo.get("web_url"):
                            source = f"[{fname}]({finfo['web_url']})"
                        else:
                            source = fname
                        lines.append(f"  [{i}] {reason} — {source}")
                lines.append("")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _rebuild_instruction(pres_json: dict) -> dict:
        """Rebuild a PPTInstruction dict from presentation snapshot JSON."""
        slides = []
        for s in pres_json.get("slides", []):
            outputs = s.get("agent_outputs") or {}
            slide_spec = {
                "layout": s.get("layout_name", "blank"),
                "background": outputs.get("background", {}),
                "notes": outputs.get("notes", ""),
                "elements": outputs.get("elements", []),
            }
            slides.append(slide_spec)

        return {
            "meta": {
                "slide_width": 13.333,
                "slide_height": 7.5,
                "language": "zh",
            },
            "slides": slides,
        }


export_service = ExportService()
