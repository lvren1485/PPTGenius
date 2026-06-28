"""Report generator — produces markdown benchmark reports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .cost_and_time import GenerationStats
from .outline_quality import OutlineScore
from .visual_quality import VisualQualityResult


def generate_report(
    cost_stats: list[GenerationStats],
    outline_scores: list[OutlineScore],
    visual_results: list[VisualQualityResult],
    output_dir: Path,
) -> Path:
    """Generate markdown benchmark report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "benchmark_report.md"
    lines = [
        "# PPTGenius Benchmark Report",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # ── B1: Cost & Time ──
    outline_stats = [s for s in cost_stats if s.gen_type == "outline"]
    ppt_stats = [s for s in cost_stats if s.gen_type == "ppt"]

    lines.append("## B1: 生成时间与成本")
    lines.append("")
    lines.append("| 类型 | 对话数 | 平均时间 | 平均成本 (¥) | 每页成本 (¥) | 平均重试 |")
    lines.append("|------|--------|---------|-------------|-------------|---------|")

    for label, group in [("大纲", outline_stats), ("PPT", ppt_stats)]:
        if not group:
            lines.append(f"| {label} | 0 | - | - | - | - |")
            continue
        avg_time = sum(s.duration_seconds for s in group) / len(group)
        avg_cost = sum(s.total_cost for s in group) / len(group)
        avg_per_slide = sum(s.per_slide_cost for s in group) / len(group)
        avg_retry = sum(s.retry_count for s in group) / len(group)
        m, s = divmod(int(avg_time), 60)
        lines.append(
            f"| {label} | {len(group)} | {m}m {s}s | {avg_cost:.4f} | {avg_per_slide:.4f} | {avg_retry:.1f} |"
        )

    lines.append("")
    lines.append("### 详细数据")
    lines.append("")
    lines.append("| Conv | 类型 | 时间 | 成本 (¥) | 页数 | 每页成本 | 重试 | Eval 剔除时间 |")
    lines.append("|------|------|------|---------|------|---------|------|-------------|")
    for s in sorted(cost_stats, key=lambda x: x.conv_id):
        lines.append(
            f"| {s.conv_title[:25]} | {s.gen_type} | {s.duration_display} | "
            f"{s.total_cost:.4f} | {s.slide_count} | {s.per_slide_cost:.4f} | "
            f"{s.retry_count} | {s.eval_excluded_seconds:.0f}s |"
        )

    # ── B2: Outline Quality ──
    lines.append("")
    lines.append("## B2: 大纲质量 (LLM Judge)")
    lines.append("")
    if outline_scores:
        lines.append("| 大纲 | 结构 | 连贯 | 充实 | 视觉 | **均分** | Judge 成本 |")
        lines.append("|------|------|------|------|------|---------|-----------|")
        for os in outline_scores:
            fs = os.final_scores
            lines.append(
                f"| {os.conv_title[:25]} | {fs.get('structure', 0):.0f} | "
                f"{fs.get('coherence', 0):.0f} | {fs.get('richness', 0):.0f} | "
                f"{fs.get('visual', 0):.0f} | **{os.avg_score:.1f}** | ¥{os.judge_cost:.4f} |"
            )
        avg_all = sum(o.avg_score for o in outline_scores) / len(outline_scores)
        lines.append(f"\n**全局均分: {avg_all:.1f} / 10**")
    else:
        lines.append("无大纲数据。")

    # ── B3: Visual Quality ──
    lines.append("")
    lines.append("## B3: PPT 视觉质量")
    lines.append("")
    if visual_results:
        lines.append("| PPT | 元素数 | 越界率 | 重叠率 | 溢出率 | 背景率 | Part完成率 | 装饰冲突 |")
        lines.append("|-----|--------|--------|--------|--------|--------|----------|---------|")
        for vr in visual_results:
            pcr = vr.part_completion_rate
            pcr_str = f"{pcr:.1%}" if pcr is not None else "—"
            lines.append(
                f"| {vr.conv_title[:25]} | {vr.total_elements} | "
                f"{vr.out_of_bounds_rate:.1%} | {vr.overlap_rate:.1%} | "
                f"{vr.text_overflow_rate:.1%} | {vr.background_rate:.1%} | "
                f"{pcr_str} | {vr.decor_conflicts} |"
            )
    else:
        lines.append("无 PPT 数据。")

    lines.append("")
    lines.append("---")
    lines.append("*PPTGenius Benchmark · Auto-generated*")

    report_text = "\n".join(lines)
    report_path.write_text(report_text, encoding="utf-8")
    return report_path
