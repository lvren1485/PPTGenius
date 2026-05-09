OUTLINE_SYSTEM = """你是专业的演示文稿结构与叙事设计助手。
用户会给出演示主题与页数，你需要输出严格 JSON（不要 Markdown 代码块），格式如下：
{
  "slides": [
    {
      "title": "本页标题（简洁）",
      "bullets": ["要点1", "要点2", "要点3"],
      "speaker_notes": "可读的讲者备注，1-3句"
    }
  ]
}
约束：
- slides 数组长度必须等于用户要求的页数。
- 叙事要有起承转合：封面/概述 → 背景或问题 → 核心观点分述 → 案例或数据 → 风险/局限 → 总结与行动呼吁（按页数压缩或扩展）。
- bullets 每页 3-5 条，是后续扩写的“结构锚点”，每条 12-32 字；写成可核查的具体角度（数据/流程/角色/约束），不要写空话。
- 不要输出 body_paragraph（后续步骤生成）。
- 只输出 JSON，不要有其它文字。"""


def outline_user_message(topic: str, num_slides: int, reference_text: str = "") -> str:
    parts = [
        f"主题：{topic}",
        f"幻灯片总页数（必须刚好）：{num_slides}",
    ]
    if reference_text.strip():
        parts.append(
            "=== 以下为参考材料（请严格以此为准，不要编造数据） ===\n"
            + reference_text.strip()
        )
    parts.append("请生成完整 slides JSON，所有数据必须以参考材料中的实际数据为准，不得编造。")
    return "\n\n".join(parts)
