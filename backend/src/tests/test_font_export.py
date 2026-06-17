"""Generate a sample PPT to verify Chinese font + z_order sorting.

Run:  uv run python -m src.tests.test_font_export
Output:  data/test_output/font_test.pptx
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure backend/src is on sys.path
_REPO = Path(__file__).resolve().parent.parent.parent.parent
_SRC = _REPO / "backend" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pptgenius.infrastructure.ppt_engine.generator import generate_ppt

OUTPUT_DIR = _REPO / "backend" / "data" / "test_output"


def build_instruction() -> dict:
    """Build a 6-slide PPT with z_order on every element."""
    return {
        "meta": {"slide_width": 13.333, "slide_height": 7.5, "language": "zh"},
        "slides": [
            # ── Slide 0: Title ──
            {
                "layout": "title_slide",
                "background": {"type": "solid", "color": "1a73e8"},
                "elements": [
                    {
                        "type": "textbox",
                        "position": {"left": 1.5, "top": 2.0, "width": 10.3, "height": 2.0, "z_order": 80},
                        "content": [{"paragraph": {"alignment": "center", "runs": [
                            {"text": "PPTGenius 字体 + Z-Order 测试", "font": {"name": "微软雅黑", "size": 40, "bold": True, "color": "ffffff"}},
                        ]}}],
                    },
                    {
                        "type": "textbox",
                        "position": {"left": 1.5, "top": 4.2, "width": 10.3, "height": 1.0, "z_order": 70},
                        "content": [{"paragraph": {"alignment": "center", "runs": [
                            {"text": "2024年6月 · AI驱动PPT生成平台", "font": {"name": "微软雅黑", "size": 18, "color": "c8d6e5"}},
                        ]}}],
                    },
                ],
            },
            # ── Slide 1: Z-Order 验证（关键） ──
            # Elements listed in REVERSE z_order; generator must sort them ascending.
            # After sorting: z=10 background → z=70 body → z=80 title.
            # This proves sorting works even when LLM submits out of order.
            {
                "layout": "blank",
                "background": {"type": "solid", "color": "ffffff"},
                "notes": "z_order 验证页。元素列表顺序为 80→70→60→20→10→0，生成后应按 z_order 升序排列(10→20→60→70→80)。",
                "elements": [
                    # ── HINT: listed in REVERSE z-order to prove sorting ──
                    {
                        "type": "textbox",
                        "position": {"left": 0.8, "top": 0.3, "width": 11.5, "height": 1.0, "z_order": 80},
                        "content": [{"paragraph": {"alignment": "left", "runs": [
                            {"text": "Z-Order 图层排序验证", "font": {"name": "微软雅黑", "size": 30, "bold": True, "color": "1a73e8"}},
                        ]}}],
                    },
                    {
                        "type": "textbox",
                        "position": {"left": 0.8, "top": 1.5, "width": 5.5, "height": 5.0, "z_order": 70},
                        "content": [
                            {"paragraph": {"alignment": "left", "space_after_pt": 12, "runs": [
                                {"text": "正文层 (z=70)", "font": {"name": "微软雅黑", "size": 22, "bold": True, "color": "202124"}},
                            ]}},
                            {"paragraph": {"alignment": "left", "space_after_pt": 8, "runs": [
                                {"text": "本页面元素在列表中按 z_order 降序排列(80→70→60→20→10)，但 generator 应按升序渲染(10→20→60→70→80)。", "font": {"name": "微软雅黑", "size": 16, "color": "5f6368"}},
                            ]}},
                            {"paragraph": {"alignment": "left", "space_after_pt": 8, "runs": [
                                {"text": "右侧装饰块颜色从底到顶依次为：浅灰(z=10) → 浅蓝(z=20) → 蓝色(z=60)。每个块标注了 z_order 值以验证层次。", "font": {"name": "微软雅黑", "size": 16, "color": "5f6368"}},
                            ]}},
                        ],
                    },
                    # Decorative shapes — layered from right column
                    {
                        "type": "shape",
                        "shape_type": "rounded_rectangle",
                        "position": {"left": 8.0, "top": 1.5, "width": 4.5, "height": 5.0, "z_order": 60},
                        "fill": {"type": "solid", "color": "c8d6e5"},
                        "text": [{"paragraph": {"alignment": "center", "runs": [
                            {"text": "z=60 小装饰", "font": {"name": "微软雅黑", "size": 14, "bold": True, "color": "1a73e8"}},
                        ]}}],
                    },
                    {
                        "type": "shape",
                        "shape_type": "rounded_rectangle",
                        "position": {"left": 8.0, "top": 1.5, "width": 4.5, "height": 3.5, "z_order": 20},
                        "fill": {"type": "solid", "color": "e8eaf6"},
                        "text": [{"paragraph": {"alignment": "center", "runs": [
                            {"text": "z=20 大装饰", "font": {"name": "微软雅黑", "size": 14, "bold": True, "color": "3f51b5"}},
                        ]}}],
                    },
                    {
                        "type": "shape",
                        "shape_type": "rectangle",
                        "position": {"left": 8.0, "top": 1.5, "width": 4.5, "height": 5.0, "z_order": 10},
                        "fill": {"type": "solid", "color": "f5f5f5"},
                        "line": {"color": "dadce0", "width_pt": 1.0},
                        "text": [{"paragraph": {"alignment": "center", "runs": [
                            {"text": "z=10 背景层", "font": {"name": "微软雅黑", "size": 14, "bold": True, "color": "9aa0a6"}},
                        ]}}],
                    },
                ],
            },
            # ── Slide 2: 表格 ──
            {
                "layout": "content_table",
                "background": {"type": "solid", "color": "ffffff"},
                "elements": [
                    {
                        "type": "textbox",
                        "position": {"left": 0.8, "top": 0.4, "width": 11.7, "height": 0.8, "z_order": 80},
                        "content": [{"paragraph": {"alignment": "left", "runs": [
                            {"text": "表格中的中文字体验证", "font": {"name": "微软雅黑", "size": 28, "bold": True, "color": "1a73e8"}},
                        ]}}],
                    },
                    {
                        "type": "table",
                        "position": {"left": 0.8, "top": 1.6, "width": 11.7, "height": 4.5, "z_order": 50},
                        "rows": 5, "cols": 4,
                        "col_widths": [2.5, 3.5, 2.8, 2.9],
                        "header": {"row": 0, "fill": "1a73e8", "font_color": "ffffff", "font_bold": True, "font_size": 16},
                        "style": {"border_color": "dadce0", "border_width_pt": 0.5, "stripe_even": "f0f4ff"},
                        "cells": [
                            {"row": 0, "col": 0, "text": "功能模块", "font": {"name": "微软雅黑", "size": 16, "bold": True, "color": "ffffff"}},
                            {"row": 0, "col": 1, "text": "技术方案", "font": {"name": "微软雅黑", "size": 16, "bold": True, "color": "ffffff"}},
                            {"row": 0, "col": 2, "text": "状态", "font": {"name": "微软雅黑", "size": 16, "bold": True, "color": "ffffff"}},
                            {"row": 0, "col": 3, "text": "完成日期", "font": {"name": "微软雅黑", "size": 16, "bold": True, "color": "ffffff"}},
                            {"row": 1, "col": 0, "text": "大纲生成", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            {"row": 1, "col": 1, "text": "LLM + RAG 知识检索增强生成", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            {"row": 1, "col": 2, "text": "已完成", "font": {"name": "微软雅黑", "size": 14, "color": "34a853"}},
                            {"row": 1, "col": 3, "text": "2024-05-20", "font": {"name": "微软雅黑", "size": 14, "color": "5f6368"}},
                            {"row": 2, "col": 0, "text": "风格选择", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            {"row": 2, "col": 1, "text": "AI Agent 自适应配色 + 布局", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            {"row": 2, "col": 2, "text": "已完成", "font": {"name": "微软雅黑", "size": 14, "color": "34a853"}},
                            {"row": 2, "col": 3, "text": "2024-05-22", "font": {"name": "微软雅黑", "size": 14, "color": "5f6368"}},
                            {"row": 3, "col": 0, "text": "PPT 生成引擎", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            {"row": 3, "col": 1, "text": "python-pptx + 结构化指令 JSON", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            {"row": 3, "col": 2, "text": "迭代中", "font": {"name": "微软雅黑", "size": 14, "color": "fbbc04"}},
                            {"row": 3, "col": 3, "text": "2024-06-15", "font": {"name": "微软雅黑", "size": 14, "color": "5f6368"}},
                            {"row": 4, "col": 0, "text": "字体渲染修复", "font": {"name": "微软雅黑", "size": 14, "bold": True, "color": "ea4335"}},
                            {"row": 4, "col": 1, "text": "lxml 注入 a:ea / a:cs typeface", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            {"row": 4, "col": 2, "text": "本次修复", "font": {"name": "微软雅黑", "size": 14, "bold": True, "color": "ea4335"}},
                            {"row": 4, "col": 3, "text": "2024-06-16", "font": {"name": "微软雅黑", "size": 14, "color": "5f6368"}},
                        ],
                    },
                ],
            },
            # ── Slide 3: 图表 ──
            {
                "layout": "content_chart",
                "background": {"type": "solid", "color": "f8f9fa"},
                "elements": [
                    {
                        "type": "textbox",
                        "position": {"left": 0.8, "top": 0.4, "width": 11.7, "height": 0.7, "z_order": 80},
                        "content": [{"paragraph": {"alignment": "left", "runs": [
                            {"text": "图表中的中文字体渲染", "font": {"name": "微软雅黑", "size": 28, "bold": True, "color": "1a73e8"}},
                        ]}}],
                    },
                    {
                        "type": "chart",
                        "chart_type": "column_clustered",
                        "position": {"left": 0.8, "top": 1.5, "width": 7.5, "height": 5.0, "z_order": 40},
                        "title": "各季度营收对比（单位：百万元）",
                        "data": {
                            "categories": ["2024Q1", "2024Q2", "2024Q3", "2024Q4"],
                            "series": [
                                {"name": "产品A", "values": [120, 145, 168, 192]},
                                {"name": "产品B", "values": [85, 98, 112, 130]},
                                {"name": "产品C", "values": [65, 72, 68, 75]},
                            ],
                        },
                        "style": {
                            "has_legend": True, "legend_position": "bottom",
                            "series_colors": ["1a73e8", "34a853", "fbbc04"],
                            "chart_area_fill": "ffffff", "title_font_size": 16, "axis_font_size": 12,
                        },
                    },
                    {
                        "type": "textbox",
                        "position": {"left": 8.8, "top": 1.5, "width": 3.7, "height": 5.0, "z_order": 70},
                        "content": [
                            {"paragraph": {"alignment": "left", "space_after_pt": 10, "runs": [
                                {"text": "关键发现", "font": {"name": "微软雅黑", "size": 20, "bold": True, "color": "202124"}},
                            ]}},
                            {"paragraph": {"alignment": "left", "space_after_pt": 8, "runs": [
                                {"text": "1. 产品A全年增长60%，Q4达到峰值1.92亿。", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            ]}},
                            {"paragraph": {"alignment": "left", "space_after_pt": 8, "runs": [
                                {"text": "2. 产品B稳步增长，年度复合增长率约15%。", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            ]}},
                            {"paragraph": {"alignment": "left", "space_after_pt": 0, "runs": [
                                {"text": "3. 产品C表现平稳，建议加大研发投入。", "font": {"name": "微软雅黑", "size": 14, "color": "202124"}},
                            ]}},
                        ],
                    },
                ],
            },
            # ── Slide 4: Ending ──
            {
                "layout": "ending",
                "background": {"type": "solid", "color": "1a73e8"},
                "elements": [
                    {
                        "type": "textbox",
                        "position": {"left": 1.5, "top": 2.5, "width": 10.3, "height": 1.5, "z_order": 80},
                        "content": [{"paragraph": {"alignment": "center", "runs": [
                            {"text": "感谢观看", "font": {"name": "微软雅黑", "size": 42, "bold": True, "color": "ffffff"}},
                        ]}}],
                    },
                    {
                        "type": "textbox",
                        "position": {"left": 1.5, "top": 4.2, "width": 10.3, "height": 0.8, "z_order": 70},
                        "content": [{"paragraph": {"alignment": "center", "runs": [
                            {"text": "PPTGenius · AI 驱动 PPT 生成平台", "font": {"name": "微软雅黑", "size": 18, "color": "c8d6e5"}},
                        ]}}],
                    },
                ],
            },
        ],
    }


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    instruction = build_instruction()
    output_path = str(OUTPUT_DIR / "font_test.pptx")

    print(f"Generating PPT with {len(instruction['slides'])} slides...")
    result = await generate_ppt(instruction, output_path)

    if result["ok"]:
        print(f"OK: {result['path']}")
        print(f"Slides: {result['slide_count']}, Size: {result['file_size']:,} bytes")
        _inspect_first_run(output_path)
        _verify_z_order(output_path)
    else:
        print(f"FAILED: {json.dumps(result['errors'], ensure_ascii=False, indent=2)}")
        sys.exit(1)


def _inspect_first_run(pptx_path: str) -> None:
    from pptx import Presentation
    from lxml import etree

    prs = Presentation(pptx_path)
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        rPr = run._r.find("{http://schemas.openxmlformats.org/drawingml/2006/main}rPr")
                        if rPr is not None:
                            xml_str = etree.tostring(rPr, encoding="unicode", pretty_print=True)
                            print("\n── First run <a:rPr> (verify ea/cs present) ──")
                            print(xml_str[:800])
                        return


def _verify_z_order(pptx_path: str) -> None:
    """Verify slide 1 shapes are sorted by z_order, not input order.

    Slide 1 was defined as: title(z=80), body(z=70), small_decoration(z=60),
    big_decoration(z=20), background(z=10).  After sorting: 10→20→60→70→80.
    """
    from pptx import Presentation
    from pptx.oxml.ns import qn

    prs = Presentation(pptx_path)

    # Get slide 1 (index 1)
    slides = list(prs.slides)
    if len(slides) < 2:
        print("\n── Z-Order: Not enough slides to verify ──")
        return

    slide = slides[1]
    shapes = list(slide.shapes)
    print(f"\n── Z-Order Verification (slide 1, {len(shapes)} shapes) ──")
    print(f"Expected render order: z=10 -> z=20 -> z=60 -> z=70 -> z=80")

    # Read shape names and first text to identify them
    shape_info = []
    for i, shape in enumerate(shapes):
        text_snippet = ""
        if shape.has_text_frame:
            text_snippet = shape.text_frame.text[:50]
        shape_info.append((i, shape.shape_id, shape.name, text_snippet))

    print(f"Actual render order (shape list):")
    for idx, sid, name, text in shape_info:
        print(f"  [{idx}] id={sid} name='{name}' text='{text}'")

    # Extract z_order hints from text to verify sequence
    z_sequence = []
    for _, _, _, text in shape_info:
        import re
        m = re.search(r'z=(\d+)', text)
        if m:
            z_sequence.append(int(m.group(1)))

    if z_sequence:
        is_sorted = all(z_sequence[i] <= z_sequence[i+1] for i in range(len(z_sequence)-1))
        print(f"\nZ-order sequence: {z_sequence}")
        print(f"Ascending (correct): {is_sorted}")
        if is_sorted:
            print("[OK] Z-order sorting works correctly!")
        else:
            print("[FAIL] Z-order sorting FAILED — shapes not in ascending order")
    else:
        print("(no z_order labels found in shape text — manual verification needed)")


if __name__ == "__main__":
    asyncio.run(main())
