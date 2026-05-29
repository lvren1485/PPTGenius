"""Benchmark — token cost, outline quality, knowledge traceability.

Run:
    cd backend
    uv run python src/benchmark.py

Output:  ../../docs/benchmark_report.html  (project-root docs/)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

# Silence most logging during benchmark
logging.basicConfig(level=logging.WARNING)
logging.getLogger("pptgenius").setLevel(logging.WARNING)

# Ensure backend/src is importable
_src = Path(__file__).resolve().parent
sys.path.insert(0, str(_src))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sqlalchemy import select

from pptgenius.infrastructure.db import Database
from pptgenius.infrastructure.db.engine import get_sessionmaker
from pptgenius.infrastructure.db.models import (
    Conversation,
    Message,
    Outline,
    OutlineSlide,
    Presentation,
    User,
)
from pptgenius.infrastructure.rag.knowledge import knowledge_service

# ── config ──────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # PPTGenius/
_REPORT_PATH = _PROJECT_ROOT / "docs" / "benchmark_report.html"
_TRACE_TOP_K = 5
_TRACE_THRESHOLD = 1.0  # BM25 score threshold for "traceable"

_SENTENCE_RE = re.compile(r"[。.！!？?\n;；]+")

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]


# ── data model ──────────────────────────────────────────────────────────────

@dataclass
class ConvStats:
    conv_id: int
    title: str
    user_id: int
    has_ppt: bool
    message_count: int
    total_cost: float           # sum of message estimated_cost
    outline_count: int
    outline_avg_score: float | None
    outline_slide_count: int
    trace_scores: list[float] = field(default_factory=list)

    @property
    def trace_avg(self) -> float | None:
        return float(np.mean(self.trace_scores)) if self.trace_scores else None

    @property
    def category(self) -> str:
        return "PPT" if self.has_ppt else "Outline"


@dataclass
class BenchmarkResult:
    timestamp: str
    total_conversations: int
    conv_outline_only: int
    conv_with_ppt: int
    total_messages: int

    # token cost (USD)
    cost_all_total: float
    cost_outline_only_total: float
    cost_ppt_total: float
    cost_per_outline_conv: float
    cost_per_ppt_conv: float

    # outline quality
    outline_count: int
    outline_score_avg: float
    outline_score_std: float
    outline_score_min: float
    outline_score_max: float

    # traceability
    traceable_sentences: int
    total_sentences: int
    trace_ratio: float
    trace_score_avg: float

    # detail
    conv_stats: list[ConvStats]


# ── database queries ────────────────────────────────────────────────────────

async def _gather(db: Database) -> list[ConvStats]:
    """Collect conversation-level stats across all users."""
    session = db.db
    all_stats: list[ConvStats] = []

    # all users
    user_result = await session.execute(select(User))
    users = list(user_result.scalars().all())

    for user in users:
        # all non-deleted conversations for this user
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .where(Conversation.status != "deleted")
            .order_by(Conversation.created_at.asc())
        )
        conv_result = await session.execute(stmt)
        convs = list(conv_result.scalars().all())

        for conv in convs:
            # messages
            msg_stmt = (
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.idx.asc())
            )
            msg_result = await session.execute(msg_stmt)
            messages = list(msg_result.scalars().all())

            total_cost = sum(m.estimated_cost or 0 for m in messages)

            # outlines
            out_stmt = (
                select(Outline)
                .where(Outline.conversation_id == conv.id)
                .where(Outline.status != "deleted")
            )
            out_result = await session.execute(out_stmt)
            outlines = list(out_result.scalars().all())

            outline_scores = [o.eval_score for o in outlines if o.eval_score is not None]
            out_avg = float(np.mean(outline_scores)) if outline_scores else None

            # presentations (whether this conv generated a PPT)
            ppt_stmt = select(Presentation).where(
                Presentation.conversation_id == conv.id
            )
            ppt_result = await session.execute(ppt_stmt)
            has_ppt = ppt_result.scalars().first() is not None

            # slide count
            slide_count = 0
            for o in outlines:
                sl_stmt = (
                    select(OutlineSlide)
                    .where(OutlineSlide.outline_id == o.id)
                )
                sl_result = await session.execute(sl_stmt)
                slide_count += len(list(sl_result.scalars().all()))

            all_stats.append(ConvStats(
                conv_id=conv.id,
                title=conv.title or f"Conv#{conv.id}",
                user_id=user.id,
                has_ppt=has_ppt,
                message_count=len(messages),
                total_cost=total_cost,
                outline_count=len(outlines),
                outline_avg_score=out_avg,
                outline_slide_count=slide_count,
            ))

    return all_stats


# ── traceability ────────────────────────────────────────────────────────────

async def _compute_traceability(
    db: Database, stats: list[ConvStats]
) -> None:
    """For each outline slide sentence, BM25-search the user's knowledge base.
    Populates ConvStats.trace_scores in place.
    """
    for s in stats:
        if s.outline_slide_count == 0:
            continue

        session = db.db
        # get all outline slides for this conv's outlines
        out_stmt = (
            select(Outline)
            .where(Outline.conversation_id == s.conv_id)
            .where(Outline.status != "deleted")
        )
        out_result = await session.execute(out_stmt)
        outlines = list(out_result.scalars().all())

        for outline in outlines:
            sl_stmt = select(OutlineSlide).where(
                OutlineSlide.outline_id == outline.id
            )
            sl_result = await session.execute(sl_stmt)
            slides = list(sl_result.scalars().all())

            for slide in slides:
                # extract searchable text from title + notes + content
                texts: list[str] = []
                if slide.title:
                    texts.append(slide.title)
                if slide.notes:
                    texts.append(slide.notes)
                if slide.content_json:
                    try:
                        _extract_texts(slide.content_json, texts)
                    except Exception:
                        pass

                combined = " ".join(texts)
                if not combined.strip():
                    continue

                sentences = [t.strip() for t in _SENTENCE_RE.split(combined) if t.strip()]
                for sent in sentences:
                    if len(sent) < 3:
                        continue
                    try:
                        results = await knowledge_service.search(
                            user_id=s.user_id, query=sent, top_k=_TRACE_TOP_K
                        )
                        if results:
                            s.trace_scores.append(max(r["score"] for r in results))
                        else:
                            s.trace_scores.append(0.0)
                    except Exception:
                        s.trace_scores.append(0.0)


def _extract_texts(obj: Any, out: list[str]) -> None:
    """Recursively extract string values from JSON content."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _extract_texts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _extract_texts(v, out)


# ── compute benchmark ───────────────────────────────────────────────────────

def _compute(stats: list[ConvStats]) -> BenchmarkResult:
    outline_convs = [s for s in stats if not s.has_ppt]
    ppt_convs = [s for s in stats if s.has_ppt]

    cost_all = sum(s.total_cost for s in stats)
    cost_outline = sum(s.total_cost for s in outline_convs)
    cost_ppt = sum(s.total_cost for s in ppt_convs)

    all_scores = [s.outline_avg_score for s in stats if s.outline_avg_score is not None]
    all_trace = [v for s in stats for v in s.trace_scores]
    traceable = sum(1 for v in all_trace if v >= _TRACE_THRESHOLD)

    return BenchmarkResult(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_conversations=len(stats),
        conv_outline_only=len(outline_convs),
        conv_with_ppt=len(ppt_convs),
        total_messages=sum(s.message_count for s in stats),
        cost_all_total=cost_all,
        cost_outline_only_total=cost_outline,
        cost_ppt_total=cost_ppt,
        cost_per_outline_conv=(cost_outline / len(outline_convs)) if outline_convs else 0,
        cost_per_ppt_conv=(cost_ppt / len(ppt_convs)) if ppt_convs else 0,
        outline_count=len(all_scores),
        outline_score_avg=float(np.mean(all_scores)) if all_scores else 0,
        outline_score_std=float(np.std(all_scores)) if all_scores else 0,
        outline_score_min=float(min(all_scores)) if all_scores else 0,
        outline_score_max=float(max(all_scores)) if all_scores else 0,
        traceable_sentences=traceable,
        total_sentences=len(all_trace),
        trace_ratio=(traceable / len(all_trace) * 100) if all_trace else 0,
        trace_score_avg=float(np.mean(all_trace)) if all_trace else 0,
        conv_stats=stats,
    )


# ── charts ──────────────────────────────────────────────────────────────────


def _fig_to_b64(fig: plt.Figure) -> str:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


_CHART_COLORS = ["#1a73e8", "#ea4335", "#34a853", "#fbbc04", "#ab47bc", "#ff7043"]


def _chart_cost(result: BenchmarkResult) -> str:
    fig, ax = plt.subplots(figsize=(6, 4))
    cats = ["Outline Only", "With PPT"]
    vals = [result.cost_per_outline_conv, result.cost_per_ppt_conv]
    bars = ax.bar(cats, vals, color=[_CHART_COLORS[0], _CHART_COLORS[1]], width=0.45)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0002,
                f"${v:.4f}", ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_ylabel("Avg Cost (USD)", fontsize=11)
    ax.set_title("Average Token Cost per Conversation", fontsize=13, fontweight="bold")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_b64(fig)


def _chart_score_dist(result: BenchmarkResult) -> str:
    scores = [s.outline_avg_score for s in result.conv_stats if s.outline_avg_score is not None]
    if not scores:
        return ""
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(scores, bins=min(10, len(scores)), color=_CHART_COLORS[2], edgecolor="white", alpha=0.85)
    ax.axvline(result.outline_score_avg, color=_CHART_COLORS[1], linestyle="--", linewidth=2,
               label=f"Avg = {result.outline_score_avg:.2f}")
    ax.set_xlabel("Outline Eval Score", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("Outline Score Distribution", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_b64(fig)


def _chart_traceability(result: BenchmarkResult) -> str:
    # per-conversation traceability
    conv_traces = [(s.title[:30] or f"C{s.conv_id}", s.trace_avg)
                   for s in result.conv_stats if s.trace_avg is not None]
    if not conv_traces:
        return ""
    conv_traces.sort(key=lambda x: -x[1])
    labels, vals = zip(*conv_traces)
    fig, ax = plt.subplots(figsize=(8, max(4, len(labels) * 0.35)))
    colors = [_CHART_COLORS[2] if v >= _TRACE_THRESHOLD else _CHART_COLORS[1]
              for v in vals]
    ax.barh(range(len(labels)), vals, color=colors, height=0.6)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.axvline(_TRACE_THRESHOLD, color="gray", linestyle="--", linewidth=1.5,
               label=f"threshold = {_TRACE_THRESHOLD}")
    ax.set_xlabel("Avg BM25 Score", fontsize=11)
    ax.set_title("Traceability by Conversation", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, loc="lower right")
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_b64(fig)


def _chart_cost_vs_score(result: BenchmarkResult) -> str:
    points = [(s.total_cost, s.outline_avg_score, s.category, s.title[:30])
              for s in result.conv_stats if s.outline_avg_score is not None and s.total_cost > 0]
    if not points:
        return ""
    fig, ax = plt.subplots(figsize=(6, 4))
    for cat, color in [("Outline", _CHART_COLORS[0]), ("PPT", _CHART_COLORS[1])]:
        xs = [p[0] for p in points if p[2] == cat]
        ys = [p[1] for p in points if p[2] == cat]
        ax.scatter(xs, ys, c=color, label=cat, s=60, alpha=0.7, edgecolors="white")
    ax.set_xlabel("Total Cost (USD)", fontsize=11)
    ax.set_ylabel("Outline Avg Score", fontsize=11)
    ax.set_title("Cost vs Quality", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _fig_to_b64(fig)


# ── HTML report ─────────────────────────────────────────────────────────────

def _render(result: BenchmarkResult, charts: dict[str, str]) -> str:
    def _opt(val, fmt=".2f"):
        return fmt.format(val) if val is not None else "—"

    rows = ""
    for s in sorted(result.conv_stats, key=lambda x: -x.total_cost):
        rows += f"""
        <tr>
            <td>{s.title}</td>
            <td><span class="tag {'tag-ppt' if s.has_ppt else 'tag-outline'}">{s.category}</span></td>
            <td>{s.message_count}</td>
            <td>${s.total_cost:.4f}</td>
            <td>{s.outline_count}</td>
            <td>{_opt(s.outline_avg_score, '.3f')}</td>
            <td>{s.outline_slide_count}</td>
            <td>{_opt(s.trace_avg, '.3f')}</td>
        </tr>"""

    chart_html = ""
    if charts.get("cost"):
        chart_html += f'<div class="chart"><img src="data:image/png;base64,{charts["cost"]}"></div>'
    if charts.get("score_dist"):
        chart_html += f'<div class="chart"><img src="data:image/png;base64,{charts["score_dist"]}"></div>'
    if charts.get("trace"):
        chart_html += f'<div class="chart"><img src="data:image/png;base64,{charts["trace"]}"></div>'
    if charts.get("cost_vs"):
        chart_html += f'<div class="chart"><img src="data:image/png;base64,{charts["cost_vs"]}"></div>'

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPTGenius Benchmark Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 40px 20px; }}
    h1 {{ font-size: 28px; margin-bottom: 6px; }}
    .subtitle {{ color: #666; font-size: 14px; margin-bottom: 30px; }}
    h2 {{ font-size: 20px; margin: 30px 0 15px; border-bottom: 2px solid #1a73e8; padding-bottom: 6px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 30px; }}
    .card {{ background: #fff; border-radius: 10px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .card .label {{ font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: .5px; }}
    .card .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    .card .value.green {{ color: #34a853; }}
    .card .value.red {{ color: #ea4335; }}
    .card .value.blue {{ color: #1a73e8; }}
    .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
    .chart {{ background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .chart img {{ width: 100%; height: auto; }}
    .chart-full {{ grid-column: 1 / -1; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    th {{ background: #1a73e8; color: #fff; font-size: 12px; padding: 10px 14px; text-align: left; }}
    td {{ font-size: 13px; padding: 9px 14px; border-bottom: 1px solid #f0f0f0; }}
    tr:last-child td {{ border-bottom: none; }}
    .tag {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
    .tag-ppt {{ background: #e8f0fe; color: #1a73e8; }}
    .tag-outline {{ background: #fef7e0; color: #f9a825; }}
    .footer {{ text-align: center; color: #aaa; font-size: 12px; margin-top: 40px; }}
</style>
</head>
<body>
<div class="container">
    <h1>PPTGenius Benchmark Report</h1>
    <p class="subtitle">Generated: {result.timestamp} | {result.total_conversations} conversations</p>

    <h2>Summary</h2>
    <div class="cards">
        <div class="card">
            <div class="label">Conversations</div>
            <div class="value">{result.total_conversations} <span style="font-size:13px;color:#999;">({result.conv_outline_only} outline / {result.conv_with_ppt} PPT)</span></div>
        </div>
        <div class="card">
            <div class="label">Total Token Cost</div>
            <div class="value blue">${result.cost_all_total:.4f}</div>
        </div>
        <div class="card">
            <div class="label">Cost / Outline Conv</div>
            <div class="value">${result.cost_per_outline_conv:.4f}</div>
        </div>
        <div class="card">
            <div class="label">Cost / PPT Conv</div>
            <div class="value">${result.cost_per_ppt_conv:.4f}</div>
        </div>
        <div class="card">
            <div class="label">Avg Outline Score</div>
            <div class="value green">{result.outline_score_avg:.3f}</div>
        </div>
        <div class="card">
            <div class="label">Outline Score Range</div>
            <div class="value">{result.outline_score_min:.2f}–{result.outline_score_max:.2f}</div>
        </div>
        <div class="card">
            <div class="label">Traceability</div>
            <div class="value green">{result.trace_ratio:.1f}%</div>
        </div>
        <div class="card">
            <div class="label">Avg BM25 Score</div>
            <div class="value">{result.trace_score_avg:.3f}</div>
        </div>
    </div>

    <h2>Charts</h2>
    <div class="chart-grid">
        {chart_html}
    </div>

    <h2>Per-Conversation Detail</h2>
    <table>
        <thead>
            <tr><th>Title</th><th>Type</th><th>Messages</th><th>Cost</th><th>Outlines</th><th>Avg Score</th><th>Slides</th><th>Trace Avg</th></tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>

    <div class="footer">PPTGenius Benchmark · Auto-generated</div>
</div>
</body>
</html>"""


# ── main ────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 50)
    print("PPTGenius Benchmark")
    print("=" * 50)

    sm = get_sessionmaker()
    async with sm() as session:
        db = Database(session)

        # 1. Gather
        print("\n[1/3] Gathering conversation stats...")
        stats = await _gather(db)
        print(f"  Found {len(stats)} conversation(s) across all users")

        if not stats:
            print("  No data to benchmark. Exiting.")
            return

        # 2. Traceability
        print("\n[2/3] Computing traceability (BM25 per sentence)...")
        await _compute_traceability(db, stats)
        total_sents = sum(len(s.trace_scores) for s in stats)
        print(f"  Evaluated {total_sents} sentence(s) across {len(stats)} conversation(s)")

        # 3. Compute & render
        print("\n[3/3] Computing metrics & rendering report...")
        result = _compute(stats)

        charts = {
            "cost": _chart_cost(result),
            "score_dist": _chart_score_dist(result),
            "trace": _chart_traceability(result),
            "cost_vs": _chart_cost_vs_score(result),
        }

        html = _render(result, charts)
        _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _REPORT_PATH.write_text(html, encoding="utf-8")

    # ── print summary ──
    print(f"\n{'─' * 50}")
    print(f"Report:  {_REPORT_PATH}")
    print(f"{'─' * 50}")
    print(f"Conversations:      {result.total_conversations:>6}  (outline={result.conv_outline_only}, PPT={result.conv_with_ppt})")
    print(f"Total Messages:     {result.total_messages:>6}")
    print(f"Total Cost:         ${result.cost_all_total:.4f}")
    print(f"Cost / Outline:     ${result.cost_per_outline_conv:.4f}")
    print(f"Cost / PPT:         ${result.cost_per_ppt_conv:.4f}")
    print(f"Avg Outline Score:  {result.outline_score_avg:.3f}  (σ={result.outline_score_std:.3f}, [{result.outline_score_min:.2f}, {result.outline_score_max:.2f}])")
    print(f"Traceability:       {result.trace_ratio:.1f}%  ({result.traceable_sentences}/{result.total_sentences} sentences, avg BM25={result.trace_score_avg:.3f})")
    print(f"{'─' * 50}")


if __name__ == "__main__":
    asyncio.run(main())
