from pathlib import Path

from ppt_generator import PPTGenerator
from ppt_generator.rag.retriever import BM25Retriever, ScoredChunk


def test_bm25_retrieve():
    path = Path(__file__).resolve().parents[1] / "knowledge" / "corpus.json"
    r = BM25Retriever.from_json_file(path)
    hits = r.retrieve("医学 影像 深度学习", top_k=2)
    assert hits
    assert any("医学" in h.text or "深度学习" in h.text for h in hits)


def test_bm25_retrieve_with_scores():
    path = Path(__file__).resolve().parents[1] / "knowledge" / "corpus.json"
    r = BM25Retriever.from_json_file(path)
    scored_hits = r.retrieve_with_scores("医学 影像 深度学习", top_k=2)
    assert scored_hits
    assert all(isinstance(h, ScoredChunk) for h in scored_hits)
    assert all(h.score >= 0 for h in scored_hits)
    assert any("医学" in h.chunk.text or "深度学习" in h.chunk.text for h in scored_hits)


def test_end_to_end_mock(tmp_path):
    gen = PPTGenerator(knowledge_json=tmp_path / "missing.json")
    outline = gen.generate_outline(topic="测试主题", num_slides=3)
    assert len(outline.slides) == 3
    enhanced = gen.enhance_with_rag(outline)
    out = tmp_path / "t_no_corpus.pptx"
    enhanced.export(out)
    assert out.is_file()

    gen2 = PPTGenerator()
    outline2 = gen2.generate_outline(topic="测试主题", num_slides=3)
    enhanced2 = gen2.enhance_with_rag(outline2)
    out2 = tmp_path / "t_with_corpus.pptx"
    enhanced2.export(out2)
    assert out2.is_file()
