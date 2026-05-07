"""
最小演示：生成大纲 → RAG 增强 → 导出 pptx。

用法（仓库根目录）：
  pip install -r requirements.txt
  pip install -e .
  python examples/demo_run.py

配置 LLM（可选）：
  set OPENAI_API_KEY=sk-...
  set PPTGENIUS_MODEL=gpt-4o-mini
未配置 Key 时使用内置占位大纲，仍可完整跑通 RAG 与导出。
"""

from pathlib import Path

from ppt_generator import PPTGenerator


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "output_demo.pptx"

    generator = PPTGenerator()
    outline = generator.generate_outline(
        topic="人工智能在医疗领域的应用与挑战",
        num_slides=8,
    )
    enhanced = generator.enhance_with_rag(outline)
    enhanced.export(out)
    print(f"已生成：{out}")


if __name__ == "__main__":
    main()
