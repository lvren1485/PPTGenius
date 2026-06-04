"""Benchmark — token cost, outline quality, knowledge traceability.

Run:
    cd backend
    uv run python benchmark.py

Output:
    ../docs/benchmark_report.html
    ../docs/benchmark_report.md
"""

from __future__ import annotations

import asyncio
import base64
import logging
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

# Ensure backend/src is importable (benchmark.py is now at backend/)
_src = Path(__file__).resolve().parent / "src"
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
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # PPTGenius/
_REPORT_DIR = _PROJECT_ROOT / "docs"
_CHARTS_DIR = _REPORT_DIR / "benchmark_charts"
_HTML_PATH = _REPORT_DIR / "benchmark_report.html"
_MD_PATH = _REPORT_DIR / "benchmark_report.md"
_TRACE_TOP_K = 5
_TRACE_TOP_K = 5
_DEFAULT_TRACE_THRESHOLD = 1.0  # fallback when no scores to compute median

_SENTENCE_RE = re.compile(r"[。.！!？?\n;；]+")

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]


# ── data model ──────────────────────────────────────────────────────────────

@dataclass
class ConvStats:
    conv_id: int
    title: str
    user_id: int
    conv_type: str               # "PPT" | "Outline" | "Other"
    first_outline_idx: int | None
    first_ppt_idx: int | None
    message_count: int
    total_cost: float            # sum of all AI message costs
    outline_cost: float | None   # avg cost of next-assistant after each outline document
    ppt_cost: float | None       # avg cost of next-assistant after each ppt document
    outline_count: int
    outline_avg_score: float | None
    outline_slide_count: int
    _outline_costs: list[float] = field(default_factory=list)   # raw per-document costs
    _ppt_costs: list[float] = field(default_factory=list)       # raw per-document costs
    trace_scores: list[float] = field(default_factory=list)

    @property
    def trace_avg(self) -> float | None:
        return float(np.mean(self.trace_scores)) if self.trace_scores else None


@dataclass
class BenchmarkResult:
    timestamp: str
    total_conversations: int
    conv_outline_only: int
    conv_with_ppt: int
    conv_other: int
    total_messages: int

    # token cost (USD)
    cost_all_total: float
    cost_outline_only_total: float
    cost_ppt_total: float
    cost_other_total: float
    cost_per_outline_conv: float
    cost_per_ppt_conv: float
    cost_per_other_conv: float

    # outline quality
    outline_count: int
    outline_score_avg: float
    outline_score_std: float
    outline_score_min: float
    outline_score_max: float

    # traceability
    trace_threshold: float          # dynamic threshold (median of all trace scores)
    traceable_sentences: int
    total_sentences: int
    trace_ratio: float
    trace_score_avg: float          # per-sentence average — independent of sentence count

    # detail
    conv_stats: list[ConvStats]


# ── database queries ────────────────────────────────────────────────────────

async def _gather(db: Database) -> list[ConvStats]:
    """Collect conversation-level stats.

    Categorization is now based on **document messages** (content_type='outline'/'ppt'),
    not presentation-table records. Cost is AI messages before the first document only
    (modifications are excluded).
    """
    session = db.db
    all_stats: list[ConvStats] = []

    user_result = await session.execute(select(User))
    users = list(user_result.scalars().all())

    for user in users:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .where(Conversation.status != "deleted")
            .order_by(Conversation.created_at.asc())
        )
        conv_result = await session.execute(stmt)
        convs = list(conv_result.scalars().all())

        for conv in convs:
            msg_stmt = (
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.idx.asc())
            )
            msg_result = await session.execute(msg_stmt)
            messages = list(msg_result.scalars().all())

            # Find first document message of each type (role='document')
            first_outline_idx: int | None = None
            first_ppt_idx: int | None = None
            for m in messages:
                if m.role != "document":
                    continue
                ct = (m.content_type or "").lower()
                if first_outline_idx is None and ct == "outline":
                    first_outline_idx = m.idx
                elif first_ppt_idx is None and ct == "ppt":
                    first_ppt_idx = m.idx
                if first_outline_idx is not None and first_ppt_idx is not None:
                    break

            # Outlines & presentations (DB fallback)
            out_stmt = (
                select(Outline)
                .where(Outline.conversation_id == conv.id)
                .where(Outline.status != "deleted")
            )
            out_result = await session.execute(out_stmt)
            outlines = list(out_result.scalars().all())

            ppt_stmt = select(Presentation).where(
                Presentation.conversation_id == conv.id
            )
            ppt_result = await session.execute(ppt_stmt)
            has_ppt_record = ppt_result.scalars().first() is not None

            # Category: document messages first, fall back to DB tables
            is_ppt = first_ppt_idx is not None or has_ppt_record
            is_outline = first_outline_idx is not None or bool(outlines)
            if is_ppt:
                conv_type = "PPT"
            elif is_outline:
                conv_type = "Outline"
            else:
                conv_type = "Other"

            # Cost: for each document message, take the cost of the next assistant.
            # "用户要求修改的情况不算" → all documents count (first + modifications),
            # each represents a generation round whose cost is the summary right after.
            def _cost_after_doc(doc_idx: int) -> float:
                for m in messages:
                    if m.idx > doc_idx and m.role == "assistant":
                        return m.estimated_cost or 0
                return 0.0

            outline_costs = [_cost_after_doc(m.idx) for m in messages
                             if m.role == "document" and (m.content_type or "").lower() == "outline"]
            ppt_costs = [_cost_after_doc(m.idx) for m in messages
                         if m.role == "document" and (m.content_type or "").lower() == "ppt"]

            outline_cost_val = float(np.mean(outline_costs)) if outline_costs else None
            ppt_cost_val = float(np.mean(ppt_costs)) if ppt_costs else None
            outline_costs_list = outline_costs
            ppt_costs_list = ppt_costs

            total_cost = sum((m.estimated_cost or 0) for m in messages if m.role == "assistant")

            outline_scores = [o.eval_score for o in outlines if o.eval_score is not None]
            out_avg = float(np.mean(outline_scores)) if outline_scores else None

            # Slide count
            slide_count = 0
            for o in outlines:
                sl_stmt = select(OutlineSlide).where(OutlineSlide.outline_id == o.id)
                sl_result = await session.execute(sl_stmt)
                slide_count += len(list(sl_result.scalars().all()))

            all_stats.append(ConvStats(
                conv_id=conv.id,
                title=conv.title or f"Conv#{conv.id}",
                user_id=user.id,
                conv_type=conv_type,
                first_outline_idx=first_outline_idx,
                first_ppt_idx=first_ppt_idx,
                message_count=len(messages),
                total_cost=total_cost,
                outline_cost=outline_cost_val,
                ppt_cost=ppt_cost_val,
                _outline_costs=outline_costs_list,
                _ppt_costs=ppt_costs_list,
                outline_count=len(outlines),
                outline_avg_score=out_avg,
                outline_slide_count=slide_count,
            ))

    return all_stats


# ── traceability ────────────────────────────────────────────────────────────

async def _compute_traceability(db: Database, stats: list[ConvStats]) -> None:
    """For each outline slide sentence, BM25-search the user's knowledge base.

    Populates ConvStats.trace_scores in place.  Each sentence's max BM25 score
    is recorded; sentences with no results get 0.0.
    """
    for s in stats:
        if s.outline_slide_count == 0:
            continue

        session = db.db
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
    outline_convs = [s for s in stats if s.conv_type == "Outline"]
    ppt_convs = [s for s in stats if s.conv_type == "PPT"]
    other_convs = [s for s in stats if s.conv_type == "Other"]

    # Pooled costs: all document→next_assistant costs across all conversations
    all_outline_costs = [c for s in stats for c in s._outline_costs]
    all_ppt_costs = [c for s in stats for c in s._ppt_costs]
    convs_with_outline = [s for s in stats if s._outline_costs]
    convs_with_ppt = [s for s in stats if s._ppt_costs]

    cost_all = sum(s.total_cost for s in stats)
    cost_outline = sum(all_outline_costs) if all_outline_costs else 0
    cost_ppt = sum(all_ppt_costs) if all_ppt_costs else 0
    cost_other = sum(s.total_cost for s in other_convs)

    all_scores = [s.outline_avg_score for s in stats if s.outline_avg_score is not None]
    all_trace = [v for s in stats for v in s.trace_scores]
    # Dynamic threshold: median of all trace scores (meaningful regardless of score distribution)
    trace_threshold = float(np.median(all_trace)) if all_trace else _DEFAULT_TRACE_THRESHOLD
    traceable = sum(1 for v in all_trace if v >= trace_threshold)

    return BenchmarkResult(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_conversations=len(stats),
        conv_outline_only=len(outline_convs),
        conv_with_ppt=len(ppt_convs),
        conv_other=len(other_convs),
        total_messages=sum(s.message_count for s in stats),
        cost_all_total=cost_all,
        cost_outline_only_total=cost_outline,
        cost_ppt_total=cost_ppt,
        cost_other_total=cost_other,
        cost_per_outline_conv=(cost_outline / len(convs_with_outline)) if convs_with_outline else 0,
        cost_per_ppt_conv=(cost_ppt / len(convs_with_ppt)) if convs_with_ppt else 0,
        cost_per_other_conv=(cost_other / len(other_convs)) if other_convs else 0,
        outline_count=len(all_scores),
        outline_score_avg=float(np.mean(all_scores)) if all_scores else 0,
        outline_score_std=float(np.std(all_scores)) if all_scores else 0,
        outline_score_min=float(min(all_scores)) if all_scores else 0,
        outline_score_max=float(max(all_scores)) if all_scores else 0,
        trace_threshold=trace_threshold,
        traceable_sentences=traceable,
        total_sentences=len(all_trace),
        trace_ratio=(traceable / len(all_trace) * 100) if all_trace else 0,
        trace_score_avg=float(np.mean(all_trace)) if all_trace else 0,
        conv_stats=stats,
    )


# ── helper ──────────────────────────────────────────────────────────────────

def _opt(val: Any, ndigits: int = 2) -> str:
    """Format a numeric value for display. Explicit float() avoids numpy formatting issues."""
    if val is None:
        return "—"
    return f"{float(val):.{ndigits}f}"


# ── charts ──────────────────────────────────────────────────────────────────

_CHART_COLORS = ["#1a73e8", "#ea4335", "#34a853", "#fbbc04", "#ab47bc", "#ff7043"]


def _save_chart(fig: plt.Figure, name: str) -> str:
    """Save chart as PNG and return base64 string for HTML embedding."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    fig.savefig(_CHARTS_DIR / f"{name}.png", format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _chart_score_dist(result: BenchmarkResult) -> str:
    """Histogram of outline eval scores."""
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
    return _save_chart(fig, "score_dist")


def _chart_traceability(result: BenchmarkResult) -> str:
    """Horizontal bar chart of per-conversation trace avg BM25 score."""
    conv_traces = [(s.title[:30] or f"C{s.conv_id}", s.trace_avg)
                   for s in result.conv_stats if s.trace_avg is not None]
    if not conv_traces:
        return ""
    conv_traces.sort(key=lambda x: -x[1])
    labels, vals = zip(*conv_traces)
    fig, ax = plt.subplots(figsize=(8, max(4, len(labels) * 0.35)))
    threshold = result.trace_threshold
    colors = [_CHART_COLORS[2] if v >= threshold else _CHART_COLORS[1]
              for v in vals]
    ax.barh(range(len(labels)), vals, color=colors, height=0.6)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.axvline(threshold, color="gray", linestyle="--", linewidth=1.5,
               label=f"median = {threshold:.2f}")
    ax.set_xlabel("Avg BM25 Score", fontsize=11)
    ax.set_title("Traceability by Conversation", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9, loc="lower right")
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return _save_chart(fig, "traceability")


# ── methodology ─────────────────────────────────────────────────────────────

def _methodology_md(threshold: float) -> str:
    return """
## 计算方式说明

### 对话分类

对话类型优先由消息记录中的 document 消息决定，无 document 消息时回退到数据库表：

1. 按 `idx` 顺序遍历对话的所有消息
2. 找到第一条 `role='document'` 且 `content_type='outline'` 的消息 → Outline 类型
3. 找到第一条 `role='document'` 且 `content_type='ppt'` 的消息 → PPT 类型
4. 若无 document 消息，检查 `outlines` 表和 `presentations` 表作为回退
5. 优先级：PPT > Outline > Other
6. 仅取第一条对应类型的 document 消息，**后续修改不纳入统计**

### 费用计算

- 对每条 `role='document'` 消息，取其后第一条 `role='assistant'` 消息的 `estimated_cost`
- **Outline 成本**：所有 outline document 对应的 next-assistant cost 的全量平均值
- **PPT 成本**：所有 ppt document 对应的 next-assistant cost 的全量平均值
- 同一对话有多条同类型 document 时（含修改），每条 document 的成本均参与平均
- 对话的 Total Cost = 所有 AI 消息的 `estimated_cost` 总和

### 可追溯性 (Traceability) 计算

1. 对每个大纲 slide 的文本内容（标题 + 笔记 + 正文）按句子切分
2. 每句（长度 ≥ 3）对用户的个人知识库执行 BM25 检索（top-{top_k}）
3. 取返回结果中的最高 BM25 score 作为该句的追溯分数
4. **`trace_score_avg`**：所有句子的 BM25 score 的**全局平均值**
   - 该指标与句子总数无关，不受对话数量不均衡的影响，是衡量整体可追溯性的**首要指标**
5. **`trace_ratio`**：BM25 score ≥ 中位数阈值（当前 = {threshold:.2f}）的句子占比
   - 阈值取所有句子的 BM25 score 中位数，自动适应数据分布。BM25 分数受索引大小、文档长度、查询特征等因素影响，不同数据集上分数分布差异较大，固定阈值无意义

### 大纲评分

- 每条大纲在生成时由 Evaluator Agent 打分（0-10），存储于 `outlines.eval_score`
- 同一对话可能有多条大纲（多次生成），取均值作为该对话的 Avg Score
""".format(top_k=_TRACE_TOP_K, threshold=threshold)


def _detail_table_rows(result: BenchmarkResult) -> str:
    rows = ""
    for s in sorted(result.conv_stats, key=lambda x: -x.total_cost):
        tag_class = {"PPT": "tag-ppt", "Outline": "tag-outline", "Other": "tag-other"}
        rows += f"""
        <tr>
            <td>{s.title}</td>
            <td><span class="tag {tag_class.get(s.conv_type, 'tag-other')}">{s.conv_type}</span></td>
            <td>{s.message_count}</td>
            <td>${_opt(s.total_cost, 4)}</td>
            <td>{s.outline_count}</td>
            <td>{_opt(s.outline_avg_score, 2)}</td>
            <td>{s.outline_slide_count}</td>
            <td>{_opt(s.trace_avg, 3)}</td>
        </tr>"""
    return rows


def _detail_table_md(result: BenchmarkResult) -> str:
    lines = ["| Title | Type | Msgs | Cost | Outlines | Avg Score | Slides | Trace Avg |",
             "|-------|------|------|------|----------|-----------|--------|-----------|"]
    for s in sorted(result.conv_stats, key=lambda x: -x.total_cost):
        lines.append(
            f"| {s.title[:40]} | {s.conv_type} | {s.message_count} "
            f"| ${_opt(s.total_cost, 4)} | {s.outline_count} "
            f"| {_opt(s.outline_avg_score, 2)} | {s.outline_slide_count} "
            f"| {_opt(s.trace_avg, 3)} |"
        )
    return "\n".join(lines)


# ── HTML report ─────────────────────────────────────────────────────────────

def _render_html(result: BenchmarkResult, charts_b64: dict[str, str]) -> str:
    chart_html = ""
    if charts_b64.get("score_dist"):
        chart_html += f'<div class="chart"><img src="data:image/png;base64,{charts_b64["score_dist"]}"></div>'
    if charts_b64.get("trace"):
        chart_html += f'<div class="chart"><img src="data:image/png;base64,{charts_b64["trace"]}"></div>'

    methodology_html = _methodology_md(result.trace_threshold).replace("\n", "<br>\n")

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
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    th {{ background: #1a73e8; color: #fff; font-size: 12px; padding: 10px 14px; text-align: left; }}
    td {{ font-size: 13px; padding: 9px 14px; border-bottom: 1px solid #f0f0f0; }}
    tr:last-child td {{ border-bottom: none; }}
    .tag {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
    .tag-ppt {{ background: #e8f0fe; color: #1a73e8; }}
    .tag-outline {{ background: #fef7e0; color: #f9a825; }}
    .tag-other {{ background: #f0f0f0; color: #999; }}
    .methodology {{ background: #fff; border-radius: 10px; padding: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.08); font-size: 14px; line-height: 1.8; color: #555; }}
    .methodology h3 {{ color: #333; margin: 16px 0 8px; }}
    .methodology p {{ margin-bottom: 8px; }}
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
            <div class="value">{result.total_conversations} <span style="font-size:13px;color:#999;">({result.conv_outline_only} outline / {result.conv_with_ppt} PPT{f" / {result.conv_other} other" if result.conv_other else ""})</span></div>
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
            <div class="value green">{result.outline_score_avg:.2f}</div>
        </div>
        <div class="card">
            <div class="label">Outline Score Range</div>
            <div class="value">{result.outline_score_min:.2f}–{result.outline_score_max:.2f}</div>
        </div>
        <div class="card">
            <div class="label">Traceability Ratio</div>
            <div class="value green">{result.trace_ratio:.1f}%</div>
        </div>
        <div class="card">
            <div class="label">Avg BM25 (per-sentence)</div>
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
        <tbody>{_detail_table_rows(result)}</tbody>
    </table>

    <h2>Methodology</h2>
    <div class="methodology">{methodology_html}</div>

    <div class="footer">PPTGenius Benchmark · Auto-generated</div>
</div>
</body>
</html>"""


# ── Markdown report ─────────────────────────────────────────────────────────

def _render_md(result: BenchmarkResult) -> str:
    extra_type = f" / {result.conv_other} other" if result.conv_other else ""

    return f"""# PPTGenius Benchmark Report

**Generated**: {result.timestamp} | **{result.total_conversations} conversations**

## Summary

| Metric | Value |
|--------|-------|
| Conversations | {result.total_conversations} (Outline: {result.conv_outline_only}, PPT: {result.conv_with_ppt}{extra_type}) |
| Total Messages | {result.total_messages} |
| Total Token Cost | ${result.cost_all_total:.4f} |
| Cost / Outline Conv | ${result.cost_per_outline_conv:.4f} |
| Cost / PPT Conv | ${result.cost_per_ppt_conv:.4f} |
| Avg Outline Score | {result.outline_score_avg:.2f} (sd={result.outline_score_std:.2f}, range=[{result.outline_score_min:.2f}, {result.outline_score_max:.2f}]) |
| Traceability Ratio | {result.trace_ratio:.1f}% ({result.traceable_sentences}/{result.total_sentences} sentences above median={result.trace_threshold:.2f}) |
| Avg BM25 Score (per-sentence) | {result.trace_score_avg:.3f} |

## Outline Score Distribution

![Outline Score Distribution](benchmark_charts/score_dist.png)

## Traceability by Conversation

![Traceability by Conversation](benchmark_charts/traceability.png)

## Per-Conversation Detail

{_detail_table_md(result)}
{_methodology_md(result.trace_threshold)}

---
*PPTGenius Benchmark · Auto-generated*
"""


# ── main ────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 50)
    print("PPTGenius Benchmark")
    print("=" * 50)

    sm = get_sessionmaker()
    async with sm() as session:
        db = Database(session)

        # 1. Gather
        print("\n[1/4] Gathering conversation stats...")
        stats = await _gather(db)
        outline_n = sum(1 for s in stats if s.conv_type == "Outline")
        ppt_n = sum(1 for s in stats if s.conv_type == "PPT")
        other_n = sum(1 for s in stats if s.conv_type == "Other")
        print(f"  Found {len(stats)} conversation(s): {outline_n} outline, {ppt_n} PPT, {other_n} other")

        if not stats:
            print("  No data to benchmark. Exiting.")
            return

        # 2. Traceability
        print("\n[2/4] Computing traceability (BM25 per sentence)...")
        await _compute_traceability(db, stats)
        total_sents = sum(len(s.trace_scores) for s in stats)
        print(f"  Evaluated {total_sents} sentence(s) across {len(stats)} conversation(s)")

        # 3. Compute metrics
        print("\n[3/4] Computing metrics...")
        result = _compute(stats)

        # 4. Charts & reports
        print("\n[4/4] Rendering charts & reports...")
        _CHARTS_DIR.mkdir(parents=True, exist_ok=True)

        charts_b64 = {
            "score_dist": _chart_score_dist(result),
            "trace": _chart_traceability(result),
        }

        html = _render_html(result, charts_b64)
        md = _render_md(result)

        _HTML_PATH.write_text(html, encoding="utf-8")
        _MD_PATH.write_text(md, encoding="utf-8")

    # ── print summary ──
    print(f"\n{'─' * 50}")
    print(f"HTML:    {_HTML_PATH}")
    print(f"MD:      {_MD_PATH}")
    print(f"Charts:  {_CHARTS_DIR}")
    print(f"{'─' * 50}")
    print(f"Conversations:      {result.total_conversations:>6}  (outline={result.conv_outline_only}, PPT={result.conv_with_ppt}, other={result.conv_other})")
    print(f"Total Messages:     {result.total_messages:>6}")
    print(f"Total Cost:         ${result.cost_all_total:.4f}")
    print(f"Cost / Outline:     ${result.cost_per_outline_conv:.4f}")
    print(f"Cost / PPT:         ${result.cost_per_ppt_conv:.4f}")
    print(f"Avg Outline Score:  {result.outline_score_avg:.2f}  (sd={result.outline_score_std:.2f}, [{result.outline_score_min:.2f}, {result.outline_score_max:.2f}])")
    print(f"Traceability:       {result.trace_ratio:.1f}%  ({result.traceable_sentences}/{result.total_sentences} sentences above median={result.trace_threshold:.2f}, avg BM25={result.trace_score_avg:.3f})")
    print(f"{'─' * 50}")


if __name__ == "__main__":
    asyncio.run(main())
