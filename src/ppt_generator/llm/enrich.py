from __future__ import annotations

import json
import re
from typing import List, Optional

from openai import OpenAI

from ppt_generator.outline.models import Outline, SlideSpec
from ppt_generator.rag.retriever import BM25Retriever, CorpusChunk

ENRICH_SYSTEM = """你是资深演示文稿撰稿与汇报教练，擅长把材料写成“可直接上台讲”的页面正文。
你将收到：整册主题、当前页序号、当前页标题与锚点要点，以及若干段素材（含来源标签）。
请把这些素材**写进幻灯片正文**：要先有一段连贯叙述，再用条目把细节拆开，条目里优先写入素材中的事实、流程、条件、数字与术语。

硬性输出：只输出严格 JSON（不要 Markdown），格式：
{
  "title": "本页标题（可在原基础上微调，使之更准确）",
  "body_paragraph": "2-4 句中文段落，信息密度高，承接标题",
  "bullets": ["4-7 条要点，每条尽量完整表达一个判断/步骤/证据，允许更长（可到 80 字）"],
  "speaker_notes": "讲者口头展开的提示：例子、过渡句、需要强调的一句结论（不超过 6 句）",
  "citations": ["用简短一行说明本页正文主要依据了哪些来源标签（不必逐字复述片段）"]
}

写作风格（很重要）：
- 少用模板腔与空话；避免高频堆砌：综上所述、总而言之、赋能、赛道、痛点、抓手、闭环、沉淀、打通、极致、协同、落地、双刃剑、不言而喻、值得注意的是、随着……的发展。
- 多用具体主语与动词；能引用素材里的名词/数字就引用；不要编造不存在的数据。
- 若素材不足以支撑某个判断，把语气改成“倾向/可能/需要验证”，不要硬编。
- 用户标签为「用户资料」的片段优先融合进正文（可在 citations 里点名文件名）。
"""


def _clip(s: str, n: int) -> str:
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _split_sentences(text: str) -> List[str]:
    text = text.replace("\r", "\n")
    parts = re.split(r"(?<=[。！？；\n])", text)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 8:
            out.append(p)
    return out


def _materials_block(chunks: List[CorpusChunk], max_chars: int = 4200) -> str:
    blocks: List[str] = []
    for i, c in enumerate(chunks, 1):
        tag = "用户资料" if c.from_user else "参考资料"
        blocks.append(f"{i}. [{tag} | {c.source_id}]\n{c.text.strip()}")
    raw = "\n\n".join(blocks)
    return raw[:max_chars]


def _merge_notes(base_notes: str, citations: List[str], refs: List[str]) -> str:
    parts: List[str] = []
    base_notes = base_notes.strip()
    if base_notes:
        parts.append(base_notes)
    if citations:
        parts.append("素材对应：" + "；".join(citations[:6]))
    if refs:
        parts.append("片段来源：" + "、".join(refs[:8]))
    return "\n\n".join(parts).strip()


def _heuristic_enrich_slide(
    topic: str,
    slide: SlideSpec,
    hits: List[CorpusChunk],
    slide_index: int,
    total_slides: int,
) -> SlideSpec:
    ordered = sorted(hits, key=lambda c: (not c.from_user, len(c.text)), reverse=True)
    merged = "\n".join(c.text.strip() for c in ordered if c.text.strip())
    sents = _split_sentences(merged)

    if slide_index == 0:
        body = f"本次演示围绕「{topic}」展开。{' '.join(slide.bullets[:2])}".strip()
        body = _clip(body, 320)
        bullets_out = []
        for b in slide.bullets:
            bullets_out.append(_clip(b, 120))
        for s in sents[:6]:
            if len(bullets_out) >= 7:
                break
            line = _clip(s.replace("\n", ""), 140)
            if line and line not in bullets_out:
                bullets_out.append(line)
        while len(bullets_out) < 4:
            bullets_out.append(_clip(f"与「{topic}」相关的背景信息与范围界定。", 120))
        refs = list(dict.fromkeys(h.source_id for h in hits[:8]))
        notes = _merge_notes(slide.speaker_notes, [], refs)
        return SlideSpec(
            title=slide.title,
            bullets=bullets_out[:7],
            body_paragraph=body,
            speaker_notes=notes,
            rag_sources=[],
        )

    if not sents:
        seed = " ".join(slide.bullets)
        body = _clip(f"{slide.title}：{seed}", 360)
        if len(body) < 60:
            body = _clip(f"结合主题「{topic}」，本页说明「{slide.title}」的关键信息与判断口径。", 360)
        bullets_out = [_clip(b, 140) for b in slide.bullets]
        while len(bullets_out) < 5:
            bullets_out.append(
                _clip(f"围绕「{slide.title}」补充一项需要在现场解释清楚的细节（结合「{topic}」语境）。", 140)
            )
        notes = _merge_notes(slide.speaker_notes, [], [])
        return SlideSpec(
            title=slide.title,
            bullets=bullets_out[:7],
            body_paragraph=body,
            speaker_notes=notes,
            rag_sources=[],
        )

    body = "".join(sents[:3])
    body = _clip(body.replace("\n", ""), 520)
    bullets_out: List[str] = []
    for s in sents[3:14]:
        if len(bullets_out) >= 7:
            break
        line = _clip(s.replace("\n", ""), 160)
        if line:
            bullets_out.append(line)
    anchor_extra = [_clip(b, 160) for b in slide.bullets if b.strip()]
    for b in anchor_extra:
        if len(bullets_out) >= 7:
            break
        if b not in bullets_out:
            bullets_out.insert(0, b)

    while len(bullets_out) < 5 and sents:
        extra = _clip(sents[min(len(bullets_out), len(sents) - 1)], 160)
        if extra not in bullets_out:
            bullets_out.append(extra)

    refs = list(dict.fromkeys(h.source_id for h in hits[:10]))
    user_refs = list(dict.fromkeys(h.source_id for h in hits if h.from_user))[:4]
    cite_lines = []
    if user_refs:
        cite_lines.append("正文优先融入了用户上传：" + "、".join(user_refs))
    if refs:
        cite_lines.append("另外参考：" + "、".join([r for r in refs if r not in user_refs][:6]))

    notes = _merge_notes(slide.speaker_notes, cite_lines, refs)
    return SlideSpec(
        title=slide.title,
        bullets=bullets_out[:7],
        body_paragraph=body,
        speaker_notes=notes,
        rag_sources=[],
    )


def _parse_enrich_json(raw: str) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("enrich json not object")
    return data


def _llm_enrich_slide(
    client: OpenAI,
    model: str,
    topic: str,
    slide: SlideSpec,
    hits: List[CorpusChunk],
    slide_index: int,
    total_slides: int,
) -> SlideSpec:
    materials = _materials_block(hits)
    user_msg = (
        f"整册主题：{topic}\n"
        f"页码：第 {slide_index + 1} / {total_slides} 页\n"
        f"当前标题：{slide.title}\n"
        f"结构锚点要点（必须覆盖其意图，但不能只复述短语）：\n"
        + "\n".join(f"- {b}" for b in slide.bullets)
        + "\n\n素材片段（允许节选融合进正文；不要机械罗列片段）：\n"
        + (materials if materials.strip() else "（暂无检索片段：请基于主题与锚点要点写成仍有信息量的正文，避免空话；不要编造数字。）")
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ENRICH_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.45,
    )
    content = (resp.choices[0].message.content or "").strip()
    data = _parse_enrich_json(content)

    title = str(data.get("title") or slide.title).strip() or slide.title
    body_paragraph = str(data.get("body_paragraph") or "").strip()
    bullets = data.get("bullets") or []
    if isinstance(bullets, str):
        bullets = [bullets]
    bullets = [str(b).strip() for b in bullets if str(b).strip()]
    notes = str(data.get("speaker_notes") or "").strip()
    citations = data.get("citations") or []
    if isinstance(citations, str):
        citations = [citations]
    citations = [str(c).strip() for c in citations if str(c).strip()]

    refs = list(dict.fromkeys(h.source_id for h in hits[:10]))
    merged_notes = _merge_notes(notes or slide.speaker_notes, citations, refs)

    if len(body_paragraph) < 40 or len(bullets) < 4:
        raise ValueError("enrich output too thin")

    return SlideSpec(
        title=title,
        bullets=bullets[:8],
        body_paragraph=_clip(body_paragraph, 900),
        speaker_notes=merged_notes,
        rag_sources=[],
    )


def enrich_outline(
    outline: Outline,
    retriever: Optional[BM25Retriever],
    client: Optional[OpenAI],
    model: str,
    top_k: int = 10,
) -> Outline:
    """用检索素材重写每一页：正文段落 + 详细要点；溯源写入备注而非正文。"""
    total = len(outline.slides)
    out_slides: List[SlideSpec] = []
    for idx, slide in enumerate(outline.slides):
        hits: List[CorpusChunk] = []
        if retriever:
            q = f"{outline.topic} {slide.title} {' '.join(slide.bullets)}"
            hits = retriever.retrieve(q, top_k=top_k)

        if client:
            try:
                out_slides.append(_llm_enrich_slide(client, model, outline.topic, slide, hits, idx, total))
                continue
            except Exception:
                pass
        out_slides.append(_heuristic_enrich_slide(outline.topic, slide, hits, idx, total))

    return Outline(topic=outline.topic, slides=out_slides)
