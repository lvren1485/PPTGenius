from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Union

from ppt_generator.export.pptx_export import export_outline_to_pptx
from ppt_generator.llm.client import OutlineLLMClient
from ppt_generator.outline.models import Outline
from ppt_generator.rag.retriever import BM25Retriever, CorpusChunk


PathLike = Union[str, Path]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_corpus_path() -> Path:
    return _repo_root() / "knowledge" / "corpus.json"


class EnhancedPresentation:
    """经 RAG 增强后的演示文稿，支持导出为 pptx。"""

    def __init__(self, outline: Outline) -> None:
        self._outline = outline

    @property
    def outline(self) -> Outline:
        return self._outline

    def export(self, path: PathLike) -> None:
        export_outline_to_pptx(self._outline, str(path))


class PPTGenerator:
    """端到端原型：大纲生成（LLM 或可离线 Mock）+ BM25 检索增强 + pptx 导出。"""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        openai_base_url: Optional[str] = None,
        model: Optional[str] = None,
        knowledge_json: Optional[PathLike] = None,
        extra_documents: Optional[List[tuple[str, str]]] = None,
    ) -> None:
        self._llm = OutlineLLMClient(
            api_key=openai_api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=openai_base_url or os.environ.get("OPENAI_BASE_URL"),
            model=model or os.environ.get("PPTGENIUS_MODEL"),
        )
        corpus_path = Path(knowledge_json) if knowledge_json else _default_corpus_path()
        chunks: List[CorpusChunk] = []
        if corpus_path.is_file():
            chunks.extend(BM25Retriever.from_json_file(corpus_path).chunks)
        if extra_documents:
            chunks.extend(BM25Retriever.from_text_documents(extra_documents).chunks)
        self._retriever = BM25Retriever(chunks) if chunks else None

    def generate_outline(self, topic: str, num_slides: int = 10) -> Outline:
        return self._llm.generate_outline(topic=topic, num_slides=num_slides)

    def enhance_with_rag(self, outline: Outline, top_k_per_slide: int = 10) -> EnhancedPresentation:
        enriched_outline = self._llm.enrich_with_materials(
            outline, self._retriever, top_k_per_slide=top_k_per_slide
        )
        return EnhancedPresentation(enriched_outline)
