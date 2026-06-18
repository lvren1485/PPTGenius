"""Test ExportService — outline markdown + presentation PPTX from snapshots.

Run:  uv run python -m src.tests.test_export_service
Output:  data/test_output/
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent.parent
_SRC = _REPO / "backend" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pptgenius.infrastructure.db.engine import get_session_manager
from pptgenius.infrastructure.export_service import export_service

OUTPUT = _REPO / "backend" / "data" / "test_output"


def _make_outline_snapshot() -> dict:
    return {
        "title": "AI Product Launch Strategy",
        "status": "completed",
        "version": "3",
        "slide_count": 8,
        "eval_score": 8.5,
        "sections": [
            {
                "section_index": 1,
                "title": "Market Overview",
                "description": "Current AI market landscape and trends",
                "slides": [
                    {
                        "slide_index": 2,
                        "title": "AI Market Size 2024-2026",
                        "layout_type": "content",
                        "status": "completed",
                        "content_json": {
                            "main_points": [
                                "Global AI market to reach $1.8T by 2026",
                                "CAGR of 38% from 2024-2026",
                                "Enterprise AI adoption at 72%",
                            ],
                            "detailed_content": "The AI market continues its exponential growth trajectory with key sectors including healthcare, finance, and manufacturing leading adoption.",
                            "key_data": "Market Size: $500B (2024) -> $1.8T (2026)",
                            "visual_note": "Use a bar chart showing market growth projections",
                            "recommended_ppt_format": "bullet_list",
                        },
                        "notes": "Reference: Gartner 2024 AI Market Report",
                        "has_image": False,
                        "has_chart": True,
                        "citations": None,
                    },
                    {
                        "slide_index": 3,
                        "title": "Competitive Landscape",
                        "layout_type": "content_table",
                        "status": "completed",
                        "content_json": {
                            "main_points": [
                                "Top 5 players control 60% market share",
                                "Startup funding up 45% YoY",
                            ],
                            "detailed_content": "Key competitors include established tech giants and well-funded startups. Differentiation through specialized vertical solutions is emerging as the winning strategy.",
                            "key_data": "Top 3: OpenAI ($80B), Anthropic ($60B), Google DeepMind",
                            "visual_note": "Use a table to compare competitors",
                            "recommended_ppt_format": "content_table",
                        },
                        "notes": "Data as of Q1 2025",
                        "has_image": False,
                        "has_chart": False,
                    },
                ],
            },
            {
                "section_index": 2,
                "title": "Product Strategy",
                "description": "Go-to-market and positioning",
                "slides": [
                    {
                        "slide_index": 5,
                        "title": "Product Differentiation",
                        "layout_type": "two_column",
                        "status": "completed",
                        "content_json": {
                            "main_points": [
                                "Unique RAG-based knowledge engine",
                                "Multi-modal content generation",
                                "Enterprise-grade security compliance",
                            ],
                            "detailed_content": "Our product differentiates through three core pillars: advanced RAG retrieval, multi-modal capabilities, and enterprise security.",
                            "key_data": "",
                            "visual_note": "Split slide with features on left, comparison on right",
                            "recommended_ppt_format": "two_column",
                        },
                        "notes": "Key selling points for enterprise customers",
                    },
                ],
            },
        ],
    }


def _make_presentation_snapshot() -> dict:
    return {
        "status": "completed",
        "style_id": 1,
        "slide_count": 3,
        "version": 2,
        "outline_version": 3,
        "slides": [
            {
                "slide_index": 1,
                "layout_name": "title_slide",
                "status": "completed",
                "agent_outputs": {
                    "background": {"type": "gradient", "gradient_angle": 135, "gradient_stops": [
                        {"position": 0, "color": "1a237e"},
                        {"position": 1.0, "color": "3949ab"},
                    ]},
                    "notes": "Title slide — deep blue gradient for tech feel",
                    "elements": [
                        {
                            "type": "textbox",
                            "position": {"left": 1.2, "top": 2.0, "width": 11.0, "height": 1.5},
                            "content": [{"paragraph": {"alignment": "left", "runs": [
                                {"text": "AI Product Launch Strategy", "font": {"name": "微软雅黑", "size": 40, "bold": True, "color": "ffffff"}},
                            ]}}],
                        },
                        {
                            "type": "textbox",
                            "position": {"left": 1.2, "top": 3.6, "width": 10.5, "height": 0.8},
                            "content": [{"paragraph": {"alignment": "left", "runs": [
                                {"text": "Q4 2025 Go-to-Market Plan", "font": {"name": "微软雅黑", "size": 18, "color": "b3c6ff"}},
                            ]}}],
                        },
                    ],
                },
            },
            {
                "slide_index": 2,
                "layout_name": "content_bullet",
                "status": "completed",
                "agent_outputs": {
                    "background": {"type": "solid", "color": "f8f9fa"},
                    "notes": "Market overview with key growth figures",
                    "elements": [
                        {
                            "type": "textbox",
                            "position": {"left": 0.8, "top": 0.4, "width": 11.5, "height": 0.8},
                            "content": [{"paragraph": {"alignment": "left", "runs": [
                                {"text": "Market Overview", "font": {"name": "微软雅黑", "size": 30, "bold": True, "color": "1a73e8"}},
                            ]}}],
                        },
                        {
                            "type": "textbox",
                            "position": {"left": 0.8, "top": 1.6, "width": 5.5, "height": 4.5},
                            "content": [
                                {"paragraph": {"alignment": "left", "space_after_pt": 12, "runs": [
                                    {"text": "Global AI market to reach $1.8T by 2026", "font": {"name": "微软雅黑", "size": 18, "bold": True, "color": "202124"}},
                                ]}},
                                {"paragraph": {"alignment": "left", "space_after_pt": 8, "runs": [
                                    {"text": "CAGR of 38% from 2024-2026 driven by enterprise adoption and LLM commoditization.", "font": {"name": "微软雅黑", "size": 16, "color": "202124"}},
                                ]}},
                                {"paragraph": {"alignment": "left", "space_after_pt": 8, "runs": [
                                    {"text": "Enterprise AI adoption rate now at 72%, up from 55% in 2023.", "font": {"name": "微软雅黑", "size": 16, "color": "5f6368"}},
                                ]}},
                            ],
                        },
                        {
                            "type": "shape",
                            "shape_type": "rounded_rectangle",
                            "position": {"left": 0.8, "top": 6.2, "width": 11.5, "height": 0.06},
                            "fill": {"type": "solid", "color": "1a73e8"},
                        },
                    ],
                },
            },
            {
                "slide_index": 3,
                "layout_name": "ending",
                "status": "completed",
                "agent_outputs": {
                    "background": {"type": "solid", "color": "1a73e8"},
                    "notes": "Thank you slide with contact info",
                    "elements": [
                        {
                            "type": "textbox",
                            "position": {"left": 1.5, "top": 2.5, "width": 10.3, "height": 1.5},
                            "content": [{"paragraph": {"alignment": "center", "runs": [
                                {"text": "Thank You", "font": {"name": "微软雅黑", "size": 42, "bold": True, "color": "ffffff"}},
                            ]}}],
                        },
                    ],
                },
            },
        ],
    }


async def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sm = get_session_manager()
    d = sm.new_session()
    try:
        u = await d.create_user("export_test_user")
        conv = await d.create_conversation(u.id)
        outline = await d.create_outline(u.id, conv.id, "Test Outline")
        await d.set_conversation_outline(conv.id, outline.id)

        outline_snap = await d.create_outline_snapshot(
            outline_id=outline.id,
            user_id=u.id,
            conversation_id=conv.id,
            outline_version=3,
            outline_json=_make_outline_snapshot(),
        )
        print(f"Outline snapshot created: id={outline_snap.id}")

        pres = await d.create_presentation(u.id, conv.id, outline_id=outline.id)
        pres_snap = await d.create_snapshot(
            presentation_id=pres.id,
            user_id=u.id,
            conversation_id=conv.id,
            outline_version=3,
            presentation_json=_make_presentation_snapshot(),
            pres_version=2,
        )
        print(f"Presentation snapshot created: id={pres_snap.id}")

        # ── 2. Export outline markdown ──
        md_name, md_path = await export_service.export_outline_md(d, outline_snap.id)
        print(f"\nOutline export: {md_path}")
        print(f"  Size: {md_path.stat().st_size} bytes")
        print("  First lines:")
        for line in md_path.read_text("utf-8").splitlines()[:15]:
            print(f"    {line}")

        # ── 3. Export presentation PPTX ──
        pptx_name, pptx_path = await export_service.export_presentation_pptx(d, pres_snap.id)
        print(f"\nPPTX export: {pptx_path}")
        print(f"  Size: {pptx_path.stat().st_size:,} bytes")

        # ── 4. Verify template icons NOT deleted ──
        tabler_dir = _SRC / "pptgenius" / "resources" / "tabler"
        svg_count = len(list(tabler_dir.glob("*.svg"))) if tabler_dir.exists() else 0
        print(f"\nTabler icons: {tabler_dir} ({svg_count} SVGs)")
        assert tabler_dir.exists(), "TEMPLATE DIR WAS DELETED!"
        assert svg_count > 0, "Template SVGs missing!"
        print("  [OK] Template directory intact")

        # ── 5. Copy to test_output ──
        import shutil
        shutil.copy2(str(md_path), str(OUTPUT / "export_test_outline.md"))
        shutil.copy2(str(pptx_path), str(OUTPUT / "export_test_presentation.pptx"))
        print(f"\nCopied to {OUTPUT}:")
        for f in ["export_test_outline.md", "export_test_presentation.pptx"]:
            fp = OUTPUT / f
            print(f"  {f}: {fp.stat().st_size:,} bytes")

        print("\n[OK] All export tests passed!")

    finally:
        await sm.close(d)


if __name__ == "__main__":
    asyncio.run(main())
