"""Benchmark: compare experimental tech routes with quantitative metrics.

Run: uv run python tests/benchmark_comparison.py
"""

import time
import statistics
from pathlib import Path

from agent.rag.chunker import chunk_text
from agent.rag.parsers import parse_file
from agent.rag.parsers.pdf_parser import parse_pdf
from agent.ppt.generator import generate_presentation
from agent.ppt.templates import TEMPLATES
from agent.models.outline import PresentationOutline, SlideOutline
from agent.llm import create_llm_client


def fmt(s):
    """Format seconds."""
    if s < 1:
        return f"{s*1000:.0f}ms"
    return f"{s:.2f}s"


# ── Test 1: Chunking Strategy Comparison ──────────────────────────────

def test_chunking_strategies():
    print("\n" + "=" * 60)
    print("TEST 1: Chunking Strategy Comparison")
    print("=" * 60)

    # Use extracted text from PDF (small sample)
    sample_text = """
Quantum computing is a type of computation that harnesses the collective
properties of quantum states, such as superposition, interference, and
entanglement, to perform calculations. The devices that perform quantum
computations are known as quantum computers.

There are several types of quantum computers, including superconducting
quantum computers, trapped ion quantum computers, and photonic quantum
computers. Each type has its own advantages and challenges.

Quantum computing has potential applications in cryptography, drug discovery,
optimization problems, and machine learning. For example, Shor's algorithm
can factor large numbers exponentially faster than classical algorithms.

Grover's algorithm provides a quadratic speedup for unstructured search
problems. Quantum error correction is essential for building practical
quantum computers, as qubits are susceptible to decoherence.

The current state of quantum computing is often referred to as the NISQ
(Noisy Intermediate-Scale Quantum) era, where quantum processors have
50-100 qubits but are not yet fault-tolerant.
""" * 20  # ~3000 chars

    strategies = ["paragraph", "fixed", "sentence"]
    results = {}

    for strategy in strategies:
        start = time.monotonic()
        chunks = chunk_text(sample_text, strategy=strategy, chunk_size=300, overlap=30)
        elapsed = time.monotonic() - start
        sizes = [len(c) for c in chunks]
        results[strategy] = {
            "count": len(chunks),
            "avg_size": statistics.mean(sizes) if sizes else 0,
            "min_size": min(sizes) if sizes else 0,
            "max_size": max(sizes) if sizes else 0,
            "time": elapsed,
        }

    print(f"{'Strategy':<12} {'Chunks':<8} {'Avg':<10} {'Min':<10} {'Max':<10} {'Time':<10}")
    print("-" * 60)
    for s, r in results.items():
        print(f"{s:<12} {r['count']:<8} {r['avg_size']:<10.0f} {r['min_size']:<10} {r['max_size']:<10} {fmt(r['time']):<10}")

    return results


# ── Test 2: PDF Parsing Performance ───────────────────────────────────

def test_pdf_parsing():
    print("\n" + "=" * 60)
    print("TEST 2: PDF Parsing Performance")
    print("=" * 60)

    pdf_path = Path("resources/高等数学上.pdf")
    if not pdf_path.exists():
        print("SKIP: 高等数学上.pdf not found")
        return None

    start = time.monotonic()
    text = parse_pdf(pdf_path)
    elapsed = time.monotonic() - start

    print(f"File size: {pdf_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"Parse time: {fmt(elapsed)}")
    print(f"Extracted text: {len(text):,} chars")
    print(f"Speed: {len(text) / elapsed / 1000:.0f} chars/sec")

    return {"file_size_mb": pdf_path.stat().st_size / 1024 / 1024,
            "parse_time": elapsed, "chars": len(text)}


# ── Test 3: LLM Performance by Task Type ──────────────────────────────

def test_llm_performance():
    print("\n" + "=" * 60)
    print("TEST 3: LLM Performance by Task Type")
    print("=" * 60)

    client = create_llm_client()
    if "Mock" in type(client).__name__:
        print("SKIP: Using MockLLMClient (no API key)")
        return None

    tasks = [
        ("short_prompt", "Reply in 5 words.", ["What is AI?"]),
        ("tool_decision", "You are a PPT agent. Choose a tool: search_web, select_template, generate_ppt. Reply only with the tool name.",
         ["I need to make a presentation about machine learning. What should I do first?"]),
        ("content_gen", "Write 3 bullet points about quantum computing for a slide. Each bullet 10-15 words.",
         ["Topic: Quantum Computing Advantages"]),
        ("structured_out", "Generate JSON: {'topic': str, 'slides': [{'title': str, 'bullets': [str]}]} with 2 slides.",
         ["Topic: Artificial Intelligence"]),
    ]

    results = {}
    for task_id, system, messages in tasks:
        times = []
        tokens_in = []
        tokens_out = []
        for _ in range(2):  # 2 runs each
            start = time.monotonic()
            resp = client.chat(system=system, messages=messages)
            elapsed = time.monotonic() - start
            times.append(elapsed)
            tokens_in.append(resp.prompt_tokens)
            tokens_out.append(resp.completion_tokens)

        avg_time = statistics.mean(times)
        avg_in = statistics.mean(tokens_in)
        avg_out = statistics.mean(tokens_out)
        results[task_id] = {
            "avg_time": avg_time, "avg_in": avg_in, "avg_out": avg_out,
            "response": resp.text[:80],
        }

    print(f"{'Task':<16} {'Time':<10} {'Tokens In':<10} {'Tokens Out':<10} {'Response Sample'}")
    print("-" * 90)
    for tid, r in results.items():
        print(f"{tid:<16} {fmt(r['avg_time']):<10} {r['avg_in']:<10} {r['avg_out']:<10} {r['response'][:50]}")

    return results


# ── Test 4: PPT Template Comparison ───────────────────────────────────

def test_templates():
    print("\n" + "=" * 60)
    print("TEST 4: PPT Template Comparison")
    print("=" * 60)

    outline = PresentationOutline(
        topic="Test",
        slides=[
            SlideOutline(title="Quantum Computing", subtitle="The Future", layout_type="title"),
            SlideOutline(title="Overview", bullets=["Point 1", "Point 2", "Point 3"], layout_type="content"),
            SlideOutline(title="Section", layout_type="section"),
            SlideOutline(title="Left vs Right", bullets=["A", "B", "C", "D"], layout_type="two_column"),
            SlideOutline(title="Thank You", layout_type="ending"),
        ],
    )

    results = {}
    for name in TEMPLATES:
        outpath = Path(f"/tmp/test_template_{name}.pptx")
        start = time.monotonic()
        path = generate_presentation(outline, template_name=name, output_path=str(outpath))
        elapsed = time.monotonic() - start
        fsize = outpath.stat().st_size if outpath.exists() else 0
        results[name] = {"time": elapsed, "size_kb": fsize / 1024}
        print(f"  {name:<20} {fmt(elapsed):<10} {fsize/1024:.1f} KB")

    return results


# ── Test 5: Pipeline End-to-End Performance ───────────────────────────

def test_pipeline_performance():
    print("\n" + "=" * 60)
    print("TEST 5: Pipeline End-to-End")
    print("=" * 60)

    from agent.agents.orchestrator import Orchestrator
    import time

    start = time.monotonic()
    orch = Orchestrator()
    result = orch.run(topic="quantum computing trends", session_id="bench-test-01")
    total = time.monotonic() - start

    print(f"Total time: {fmt(total)}")
    print(f"Slides: {result.get('slide_count', 0)}")
    print(f"Session: {result.get('session_id')}")

    # Count LLM calls from logs
    log_dir = Path("logs/calls")
    bench_logs = list(log_dir.glob(f"*bench-test-01*"))
    print(f"LLM calls in this session: {len(bench_logs)}")

    return {"total_time": total, "slide_count": result.get("slide_count", 0),
            "llm_calls": len(bench_logs)}


# ── Run All ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = {}

    results["chunking"] = test_chunking_strategies()
    results["pdf"] = test_pdf_parsing()
    results["llm"] = test_llm_performance()
    results["templates"] = test_templates()
    results["pipeline"] = test_pipeline_performance()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nTest 1 - Chunking: see table above")
    if results.get("pdf"):
        print(f"Test 2 - PDF parsing: {results['pdf']['chars']:,} chars in {fmt(results['pdf']['parse_time'])}")
    if results.get("llm"):
        print(f"Test 3 - LLM avg: {fmt(statistics.mean([r['avg_time'] for r in results['llm'].values()]))} per call")
    if results.get("templates"):
        print(f"Test 4 - Templates: {len(results['templates'])} templates compared")
    if results.get("pipeline"):
        print(f"Test 5 - Pipeline: {fmt(results['pipeline']['total_time'])} total, {results['pipeline']['llm_calls']} LLM calls")
