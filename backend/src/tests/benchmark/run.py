"""Benchmark runner — CLI entry point.

Usage:
    cd backend
    uv run python -m tests.benchmark.run [--skip-judge] [--judge-model MODEL]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
logging.getLogger("pptgenius").setLevel(logging.WARNING)

_src = Path(__file__).resolve().parent.parent.parent  # backend/src/
sys.path.insert(0, str(_src))

from pptgenius.infrastructure.db.engine import get_sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # PPTGenius/
_REPORT_DIR = _PROJECT_ROOT / "docs" / "benchmark"


async def main(skip_judge: bool = False, judge_model: str = "deepseek-chat"):
    from tests.benchmark.cost_and_time import compute_cost_and_time
    from tests.benchmark.visual_quality import compute_visual_quality
    from tests.benchmark.outline_quality import compute_outline_quality
    from tests.benchmark.report import generate_report

    sm = get_sessionmaker()
    async with sm() as session:
        print("=" * 50)
        print("PPTGenius Benchmark")
        print("=" * 50)

        # B1
        print("\n[1/3] Computing cost & time from messages table...")
        cost_stats = await compute_cost_and_time(session)
        outline_n = sum(1 for s in cost_stats if s.gen_type == "outline")
        ppt_n = sum(1 for s in cost_stats if s.gen_type == "ppt")
        print(f"  Found {len(cost_stats)} generation events ({outline_n} outline, {ppt_n} PPT)")

        # B2
        outline_scores = []
        if skip_judge:
            print("\n[2/3] Skipping outline quality judge (--skip-judge)")
        else:
            print(f"\n[2/3] Scoring outlines with LLM judge ({judge_model})...")
            outline_scores = await compute_outline_quality(
                session, judge_model=judge_model,
            )
            if outline_scores:
                avg = sum(o.avg_score for o in outline_scores) / len(outline_scores)
                print(f"  Scored {len(outline_scores)} outline(s), avg = {avg:.1f}/10")
            else:
                print("  No outlines to score.")

        # B3
        print("\n[3/3] Checking PPT visual quality...")
        visual_results = await compute_visual_quality(session)
        total_slides = sum(len(v.slide_scores) for v in visual_results)
        print(f"  Checked {len(visual_results)} presentation(s), {total_slides} slides")

    # Report
    print("\nGenerating report...")
    path = generate_report(cost_stats, outline_scores, visual_results, _REPORT_DIR)
    print(f"  Report: {path}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPTGenius Benchmark")
    parser.add_argument("--skip-judge", action="store_true",
                        help="Skip LLM outline quality judge (saves API cost)")
    parser.add_argument("--judge-model", default="deepseek-chat",
                        help="Model for outline quality judge (default: deepseek-chat)")
    args = parser.parse_args()
    asyncio.run(main(skip_judge=args.skip_judge, judge_model=args.judge_model))
