"""Test ExportService — outline markdown + presentation PPTX from snapshots."""

import json
import shutil
from pathlib import Path

import pytest

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.export_service import export_service

OUTPUT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "test_output"


def _outline_snapshot_json() -> dict:
    return {
        "title": "AI Product Launch Strategy",
        "status": "completed", "version": "3", "slide_count": 8, "eval_score": 8.5,
        "sections": [{
            "section_index": 1, "title": "Market Overview",
            "description": "Current AI market landscape",
            "slides": [{
                "slide_index": 2, "title": "AI Market Size",
                "layout_type": "content", "status": "completed",
                "content_json": {
                    "main_points": ["Global AI market $1.8T by 2026", "CAGR 38%"],
                    "detailed_content": "The AI market continues exponential growth.",
                    "key_data": "Market: $500B -> $1.8T",
                    "visual_note": "Bar chart showing growth",
                    "recommended_ppt_format": "bullet_list",
                },
                "notes": "Reference: Gartner 2024",
            }],
        }],
    }


def _pres_snapshot_json() -> dict:
    return {
        "status": "completed", "style_id": 1, "slide_count": 2,
        "version": 2, "outline_version": 3,
        "slides": [{
            "slide_index": 1, "layout_name": "title_slide", "status": "completed",
            "agent_outputs": {
                "background": {"type": "solid", "color": "1a73e8"},
                "notes": "Title slide",
                "elements": [{
                    "type": "textbox",
                    "position": {"left": 1.2, "top": 2.0, "width": 11.0, "height": 1.5},
                    "content": [{"paragraph": {"alignment": "center", "runs": [
                        {"text": "AI Strategy", "font": {"name": "微软雅黑", "size": 40, "bold": True, "color": "ffffff"}},
                    ]}}],
                }],
            },
        }, {
            "slide_index": 2, "layout_name": "ending", "status": "completed",
            "agent_outputs": {
                "background": {"type": "solid", "color": "1a73e8"},
                "notes": "Thank you",
                "elements": [{
                    "type": "textbox",
                    "position": {"left": 1.5, "top": 2.5, "width": 10.3, "height": 1.5},
                    "content": [{"paragraph": {"alignment": "center", "runs": [
                        {"text": "Thank You", "font": {"name": "微软雅黑", "size": 42, "bold": True, "color": "ffffff"}},
                    ]}}],
                }],
            },
        }],
    }


class TestExportService:
    @pytest.mark.asyncio
    async def test_export_outline_markdown(self, db):
        d = Database(db)
        u = await d.create_user("exp_user")
        conv = await d.create_conversation(u.id)
        outline = await d.create_outline(u.id, conv.id, "Test Outline")
        snap = await d.create_outline_snapshot(
            outline_id=outline.id, user_id=u.id, conversation_id=conv.id,
            outline_version=3, outline_json=_outline_snapshot_json(),
        )

        filename, path = await export_service.export_outline_md(d, snap.id)
        assert path.exists()
        content = path.read_text("utf-8")
        assert "AI Product Launch Strategy" in content
        assert "### 2. AI Market Size" in content
        assert "Global AI market $1.8T" in content
        assert "Gartner 2024" in content
        print(f"  Outline export OK: {len(content)} chars")

    @pytest.mark.asyncio
    async def test_export_presentation_pptx(self, db):
        d = Database(db)
        u = await d.create_user("exp2_user")
        conv = await d.create_conversation(u.id)
        outline = await d.create_outline(u.id, conv.id, "Test Outline")
        pres = await d.create_presentation(u.id, conv.id, outline_id=outline.id)
        snap = await d.create_snapshot(
            presentation_id=pres.id, user_id=u.id, conversation_id=conv.id,
            outline_version=3, presentation_json=_pres_snapshot_json(), pres_version=2,
        )

        filename, path = await export_service.export_presentation_pptx(d, snap.id)
        assert path.exists()
        assert path.stat().st_size > 1000
        print(f"  PPTX export OK: {path.stat().st_size:,} bytes")

    @pytest.mark.asyncio
    async def test_template_icons_not_deleted(self, db):
        d = Database(db)
        u = await d.create_user("exp3_user")
        conv = await d.create_conversation(u.id)
        outline = await d.create_outline(u.id, conv.id, "Test Outline")
        pres = await d.create_presentation(u.id, conv.id, outline_id=outline.id)
        snap = await d.create_snapshot(
            presentation_id=pres.id, user_id=u.id, conversation_id=conv.id,
            outline_version=3, presentation_json=_pres_snapshot_json(), pres_version=2,
        )

        await export_service.export_presentation_pptx(d, snap.id)

        # Verify Tabler icons directory still exists
        tabler = (Path(__file__).resolve().parent.parent.parent /
            "pptgenius" / "resources" / "tabler")
        assert tabler.exists(), "TEMPLATE ICON DIRECTORY WAS DELETED!"
        svgs = list(tabler.rglob("*.svg"))
        assert len(svgs) > 0, "Template SVGs missing!"
        print(f"  Template icons OK: {len(svgs)} SVGs intact")

    @pytest.mark.asyncio
    async def test_copy_to_test_output(self, db):
        """Generate real output files for manual inspection."""
        OUTPUT.mkdir(parents=True, exist_ok=True)
        d = Database(db)
        u = await d.create_user("exp4_user")
        conv = await d.create_conversation(u.id)
        outline = await d.create_outline(u.id, conv.id, "Final Export Test")

        snap1 = await d.create_outline_snapshot(
            outline_id=outline.id, user_id=u.id, conversation_id=conv.id,
            outline_version=3, outline_json=_outline_snapshot_json(),
        )
        _, md_path = await export_service.export_outline_md(d, snap1.id)

        pres = await d.create_presentation(u.id, conv.id, outline_id=outline.id)
        snap2 = await d.create_snapshot(
            presentation_id=pres.id, user_id=u.id, conversation_id=conv.id,
            outline_version=3, presentation_json=_pres_snapshot_json(), pres_version=2,
        )
        _, pptx_path = await export_service.export_presentation_pptx(d, snap2.id)

        shutil.copy2(str(md_path), str(OUTPUT / "export_test_outline.md"))
        shutil.copy2(str(pptx_path), str(OUTPUT / "export_test_presentation.pptx"))
        print(f"  Copied to {OUTPUT}")
        assert (OUTPUT / "export_test_outline.md").exists()
        assert (OUTPUT / "export_test_presentation.pptx").exists()
