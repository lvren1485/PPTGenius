"""Test BM25 index manager."""
import os
import tempfile

from pptgenius.infrastructure.rag.bm25 import BM25Manager


class TestBM25Manager:
    @classmethod
    def setup_class(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.path = os.path.join(cls.tmp, "test.pkl")
        cls.bm = BM25Manager(cls.path)

    @classmethod
    def teardown_class(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_build_and_search(self):
        self.bm.build(["alpha beta", "alpha gamma", "beta gamma delta"])
        results = self.bm.search("alpha", top_k=2)
        assert len(results) == 2

    def test_chunk_count(self):
        self.bm.build(["a b c", "d e f"])
        assert self.bm.chunk_count == 2

    def test_save_and_load(self):
        self.bm.build(["hello world", "foo bar"])
        self.bm.save()
        bm2 = BM25Manager(self.path)
        assert bm2.load()
        assert bm2.chunk_count == 2
        results = bm2.search("hello", top_k=1)
        assert len(results) == 1

    def test_empty_build(self):
        self.bm.build([])
        assert self.bm.chunk_count == 0
        assert self.bm.search("query") == []

    def test_add(self):
        self.bm.build(["doc one"])
        self.bm.add(["doc two", "doc three"])
        assert self.bm.chunk_count == 3

    def test_remove(self):
        self.bm.build(["keep me", "drop me", "keep too"])
        removed = self.bm.remove(lambda c: "drop" in c)
        assert removed == 1
        assert self.bm.chunk_count == 2

    def test_metadata_in_search_results(self):
        """chunk_id and file_id must be returned in search results."""
        meta = [
            {"chunk_id": 10, "file_id": 1},
            {"chunk_id": 20, "file_id": 2},
            {"chunk_id": 30, "file_id": 1},
        ]
        self.bm.build(["alpha beta", "alpha gamma", "beta gamma delta"], meta=meta)
        results = self.bm.search("alpha", top_k=3)
        assert len(results) == 3
        ids = {(r["chunk_id"], r["file_id"]) for r in results}
        assert (10, 1) in ids
        assert (20, 2) in ids
        assert (30, 1) in ids

    def test_metadata_save_and_load(self):
        """Metadata must survive save/load round-trip."""
        meta = [
            {"chunk_id": 5, "file_id": 3},
            {"chunk_id": 6, "file_id": 4},
        ]
        self.bm.build(["hello world", "foo bar"], meta=meta)
        self.bm.save()
        bm2 = BM25Manager(self.path)
        assert bm2.load()
        results = bm2.search("hello", top_k=1)
        assert results[0]["chunk_id"] == 5
        assert results[0]["file_id"] == 3

    def test_metadata_add_preserves_meta(self):
        """add() must merge metadata correctly."""
        self.bm.build(["doc one"], meta=[{"chunk_id": 1, "file_id": 10}])
        self.bm.add(["doc two"], meta=[{"chunk_id": 2, "file_id": 20}])
        assert self.bm.chunk_count == 2
        results = self.bm.search("two", top_k=2)
        ids = {(r["chunk_id"], r["file_id"]) for r in results}
        assert (1, 10) in ids
        assert (2, 20) in ids

    def test_no_meta_backward_compatible(self):
        """build() without meta should not crash search."""
        self.bm.build(["plain text", "more text"])
        results = self.bm.search("plain", top_k=1)
        assert len(results) == 1
        assert "chunk" in results[0]
        assert "score" in results[0]
        # chunk_id/file_id should be absent, not None
        assert results[0].get("chunk_id") is None
        assert results[0].get("file_id") is None
