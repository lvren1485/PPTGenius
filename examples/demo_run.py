"""
最小演示：生成大纲 → RAG 增强 → 导出 pptx。

用法（仓库根目录）：
  pip install -r requirements.txt
  pip install -e .
  python examples/demo_run.py

配置 LLM（可选）：
  在 .env 文件中配置：
  OPENAI_API_KEY=...
  PPTGENIUS_MODEL=...
未配置 Key 时使用内置占位大纲，仍可完整跑通 RAG 与导出。
"""

from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from ppt_generator import PPTGenerator


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "output_demo.pptx"

    generator = PPTGenerator()
    
    # 打印配置信息，确认是否加载了 API Key
    print(f"API Key 已配置: {generator._llm._api_key is not None}")
    if generator._llm._client:
        print(f"使用模型: {generator._llm._model}")
        print("正在调用 LLM 生成大纲...")
    
    outline = generator.generate_outline(
        topic="人工智能在医疗领域的应用与挑战",
        num_slides=8,
    )
    
    print(f"大纲已生成，共 {len(outline.slides)} 页")
    print("正在进行 RAG 增强...")
    enhanced = generator.enhance_with_rag(outline)
    
    print("正在导出 PPT...")
    enhanced.export(out)
    print(f"已生成：{out}")


if __name__ == "__main__":
    main()
