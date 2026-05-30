#!/usr/bin/env python3
"""
PPT-Genius 基准测试评估脚本

用法：
  python scripts/evaluate_benchmark.py
  python scripts/evaluate_benchmark.py --benchmark benchmarks/pptgenius_benchmark.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from ppt_generator import PPTGenerator
from ppt_generator.rag.retriever import BM25Retriever, ScoredChunk


def load_benchmark(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def evaluate_source_recall(
    retriever: BM25Retriever,
    topic: str,
    expected_sources: List[str],
    top_k: int = 10,
) -> Dict[str, Any]:
    """评估预期来源召回率"""
    hits: List[ScoredChunk] = retriever.retrieve_with_scores(topic, top_k=top_k)
    retrieved_sources = set(h.chunk.source_id for h in hits)
    expected_set = set(expected_sources)
    recalled = expected_set & retrieved_sources
    recall = len(recalled) / len(expected_set) if expected_set else 1.0
    return {
        "recall": recall,
        "expected": expected_sources,
        "retrieved": list(retrieved_sources),
        "recalled": list(recalled),
    }


def evaluate_keyword_coverage(outline_text: str, keywords: List[str]) -> Dict[str, Any]:
    """评估关键词覆盖率"""
    outline_lower = outline_text.lower()
    covered = [kw for kw in keywords if kw.lower() in outline_lower]
    coverage = len(covered) / len(keywords) if keywords else 1.0
    return {
        "coverage": coverage,
        "keywords": keywords,
        "covered": covered,
    }


def outline_to_text(outline) -> str:
    """将Outline对象转换为纯文本用于关键词检查"""
    parts = [outline.topic or ""]
    for slide in outline.slides:
        parts.append(slide.title or "")
        for bullet in slide.bullets:
            parts.append(bullet)
        if slide.speaker_notes:
            parts.append(slide.speaker_notes)
        if slide.body_paragraph:
            parts.append(slide.body_paragraph)
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 PPT-Genius 基准测试")
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("benchmarks/pptgenius_benchmark.json"),
        help="基准测试 JSON 文件路径",
    )
    parser.add_argument(
        "--knowledge",
        type=Path,
        default=Path("knowledge/corpus.json"),
        help="知识库 JSON 文件路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/last_metrics.json"),
        help="评估结果输出文件",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    benchmark_path = root / args.benchmark
    knowledge_path = root / args.knowledge
    output_path = root / args.output

    print(f"加载基准测试: {benchmark_path}")
    benchmarks = load_benchmark(benchmark_path)
    print(f"加载知识库: {knowledge_path}")

    # 初始化生成器
    generator = PPTGenerator(knowledge_json=knowledge_path)
    retriever = BM25Retriever.from_json_file(knowledge_path)

    results: List[Dict[str, Any]] = []
    overall_metrics = {
        "total": len(benchmarks),
        "page_accuracy_passed": 0,
        "source_recall_passed": 0,
        "keyword_coverage_passed": 0,
        "avg_source_recall": 0.0,
        "avg_keyword_coverage": 0.0,
    }

    print(f"\n开始评估 {len(benchmarks)} 个样例...\n")

    for i, case in enumerate(benchmarks, 1):
        print(f"[{i}/{len(benchmarks)}] {case['id']} ({case['scenario']})")
        case_result: Dict[str, Any] = {"id": case["id"], "scenario": case["scenario"]}

        try:
            outline = generator.generate_outline(
                topic=case["topic"], num_slides=case["num_slides"]
            )

            page_accuracy = 1.0 if len(outline.slides) == case["num_slides"] else 0.0
            case_result["page_accuracy"] = page_accuracy
            if page_accuracy == 1.0:
                overall_metrics["page_accuracy_passed"] += 1
            print(f"  页数准确率: {page_accuracy:.0%} (期望{case['num_slides']}页，实际{len(outline.slides)}页)")

            source_result = evaluate_source_recall(
                retriever, case["topic"], case["expected_sources"]
            )
            case_result["source_recall"] = source_result
            recall = source_result["recall"]
            overall_metrics["avg_source_recall"] += recall
            if recall >= 0.8:
                overall_metrics["source_recall_passed"] += 1
            print(f"  来源召回率: {recall:.0%} (期望{case['expected_sources']}，召回{source_result['recalled']})")

            outline_text = outline_to_text(outline)
            keyword_result = evaluate_keyword_coverage(outline_text, case["keywords"])
            case_result["keyword_coverage"] = keyword_result
            coverage = keyword_result["coverage"]
            overall_metrics["avg_keyword_coverage"] += coverage
            if coverage >= 0.8:
                overall_metrics["keyword_coverage_passed"] += 1
            print(f"  关键词覆盖率: {coverage:.0%} (覆盖{len(keyword_result['covered'])}/{len(case['keywords'])})")

            enhanced = generator.enhance_with_rag(outline)
            traceable_pages = sum(
                1 for s in enhanced.outline.slides if s.rag_sources
            )
            case_result["traceable_page_ratio"] = traceable_pages / len(enhanced.outline.slides) if enhanced.outline.slides else 0.0
            print(f"  可溯源页比例: {case_result['traceable_page_ratio']:.0%}")

            case_result["status"] = "success"
        except Exception as e:
            case_result["status"] = "error"
            case_result["error"] = str(e)
            print(f"  错误: {e}")

        results.append(case_result)
        print()

    overall_metrics["avg_source_recall"] /= len(benchmarks)
    overall_metrics["avg_keyword_coverage"] /= len(benchmarks)

    print("=" * 60)
    print("总体评估结果:")
    print(f"  总样例数: {overall_metrics['total']}")
    print(f"  页数准确率: {overall_metrics['page_accuracy_passed']/len(benchmarks):.0%} ({overall_metrics['page_accuracy_passed']}/{len(benchmarks)})")
    print(f"  来源召回率(≥80%): {overall_metrics['source_recall_passed']/len(benchmarks):.0%} ({overall_metrics['source_recall_passed']}/{len(benchmarks)})")
    print(f"  关键词覆盖率(≥80%): {overall_metrics['keyword_coverage_passed']/len(benchmarks):.0%} ({overall_metrics['keyword_coverage_passed']}/{len(benchmarks)})")
    print(f"  平均来源召回率: {overall_metrics['avg_source_recall']:.0%}")
    print(f"  平均关键词覆盖率: {overall_metrics['avg_keyword_coverage']:.0%}")
    print("=" * 60)

    output = {"overall": overall_metrics, "results": results}
    output_path.parent.mkdir(exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存至: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
