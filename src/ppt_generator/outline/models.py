from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SlideSpec:
    """单页幻灯片的结构化描述。"""

    title: str
    bullets: List[str] = field(default_factory=list)
    body_paragraph: str = ""
    speaker_notes: str = ""
    rag_sources: List[str] = field(default_factory=list)


@dataclass
class Outline:
    """完整大纲（生成或经 RAG 增强后均可使用同一结构）。"""

    topic: str
    slides: List[SlideSpec]
