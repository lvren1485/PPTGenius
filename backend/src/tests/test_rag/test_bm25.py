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
