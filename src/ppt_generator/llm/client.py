from __future__ import annotations

import json
import os
from typing import List, Optional

from openai import OpenAI

from ppt_generator.llm.prompts import OUTLINE_SYSTEM, outline_user_message
from ppt_generator.outline.models import Outline, SlideSpec
from ppt_generator.rag.retriever import BM25Retriever


def _mock_outline(topic: str, num_slides: int) -> Outline:
    """无 API Key 时的确定性占位大纲，保证端到端可运行。"""
    if num_slides < 1:
        num_slides = 1

    section_cycle = [
        ("封面与主题定位", ["演示主题：" + topic, "受众与目标说明"]),
        ("目录与结构", ["本次分享的主要内容脉络", "预期收获"]),
        ("背景与问题", ["行业/场景现状概述", "核心痛点或未满足需求"]),
        ("核心概念与框架", ["关键术语界定", "整体方法论或技术路线"]),
        ("关键技术一", ["要点说明", "适用边界"]),
        ("关键技术二", ["要点说明", "与前一页的衔接"]),
        ("案例与应用场景", ["代表性案例描述", "量化或定性效果"]),
        ("挑战、风险与伦理", ["主要风险点", "合规与治理考量"]),
        ("实施路径与资源", ["落地步骤建议", "人力/数据/算力依赖"]),
        ("总结与行动呼吁", ["三条以内结论", "建议的下一步"]),
    ]

    slides: List[SlideSpec] = []
    for i in range(num_slides):
        if i == 0:
            slides.append(
                SlideSpec(
                    title=topic[:40] or "演示标题",
                    bullets=[topic, "PPT-Genius 原型演示（离线占位大纲）"],
                    body_paragraph="",
                    speaker_notes="说明演示主题与本次分享目标。",
                )
            )
            continue
        sec_title, sec_bullets = section_cycle[(i - 1) % len(section_cycle)]
        title = sec_title if i < len(section_cycle) else f"第 {i + 1} 节：深化论述"
        bullets = list(sec_bullets)
        bullets.append(f"与主题「{topic[:20]}…」的对齐说明（占位）" if len(topic) > 20 else f"与主题「{topic}」的对齐说明（占位）")
        slides.append(
            SlideSpec(
                title=title,
                bullets=bullets[:5],
                body_paragraph="",
                speaker_notes=f"围绕「{topic}」展开本页要点，可结合检索到的资料补充数据与出处。",
            )
        )
    return Outline(topic=topic, slides=slides)


def _parse_llm_json(raw: str) -> Outline:
    original_raw = raw
    # 尝试清理输出，只保留 JSON 部分
    raw = raw.strip()
    # 尝试找到 JSON 开始和结束位置
    if raw.startswith("```"):
        # 移除 Markdown 代码块标记
        lines = raw.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    
    # 尝试从第一个 { 开始解析
    start_idx = raw.find("{")
    end_idx = raw.rfind("}")
    if start_idx >= 0 and end_idx > start_idx:
        raw = raw[start_idx:end_idx+1]
    
    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            # 如果解析失败，尝试更宽松的清理
            import re
            # 移除控制字符
            raw = re.sub(r'[\x00-\x1F\x7F]', '', raw)
            # 尝试修复常见问题
            raw = raw.replace("，", ",").replace("。", ".")
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 如果还是失败，回退到 mock
            print("LLM 返回的 JSON 解析失败，使用占位大纲")
            print(f"原始输出（前500字符）: {repr(original_raw[:500])}")
            raise
    
    slides_raw = data.get("slides") or []
    slides: List[SlideSpec] = []
    for item in slides_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "未命名页面").strip()
        bullets = item.get("bullets") or []
        if isinstance(bullets, str):
            bullets = [bullets]
        bullets = [str(b).strip() for b in bullets if str(b).strip()]
        notes = str(item.get("speaker_notes") or "").strip()
        body_paragraph = str(item.get("body_paragraph") or "").strip()
        slides.append(
            SlideSpec(title=title, bullets=bullets, body_paragraph=body_paragraph, speaker_notes=notes)
        )
    if not slides:
        raise ValueError("LLM 返回的 slides 为空")
    return Outline(topic="", slides=slides)


class OutlineLLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self._model = model or os.environ.get("PPTGENIUS_MODEL", "gpt-4o-mini")
        self._client: Optional[OpenAI] = None
        if self._api_key:
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)

    def generate_outline(self, topic: str, num_slides: int, reference_text: str = "") -> Outline:
        if not self._client:
            return _mock_outline(topic, num_slides)

        user_msg = outline_user_message(topic, num_slides, reference_text)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": OUTLINE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        content = (resp.choices[0].message.content or "").strip()
        outline = _parse_llm_json(content)
        outline.topic = topic

        if len(outline.slides) != num_slides:
            if len(outline.slides) > num_slides:
                outline.slides = outline.slides[:num_slides]
            else:
                need = num_slides - len(outline.slides)
                for j in range(need):
                    outline.slides.append(
                        SlideSpec(
                            title=f"补充论述 {len(outline.slides) + 1}",
                            bullets=[
                                f"围绕主题「{topic}」的延展要点（自动补齐页）",
                                "可结合检索资料补充数据、案例与引用来源",
                            ],
                            body_paragraph="",
                            speaker_notes="",
                        )
                    )
        return outline

    def enrich_with_materials(
        self,
        outline: Outline,
        retriever: Optional[BM25Retriever] = None,
        top_k_per_slide: int = 10,
    ) -> Outline:
        """基于检索素材重写页面正文（段落 + 详细要点），引用写入备注。"""
        from ppt_generator.llm.enrich import enrich_outline

        return enrich_outline(
            outline, retriever, self._client, self._model, top_k=top_k_per_slide
        )
