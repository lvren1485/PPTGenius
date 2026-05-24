"""Integration test for KnowledgeManager — requires DB + real DOCX file."""
import tempfile
from pathlib import Path

import pytest_asyncio
from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag.knowledge_manager import KnowledgeManager
from pptgenius.infrastructure.workspace.manager import WorkspaceManager


class TestKnowledgeManager:
    @pytest_asyncio.fixture
    async def d(self, db):
        user = await Database(db).create_user("km_user")
        return Database(db), user

    async def test_ingest_and_search_md(self, db, d):
        db_obj, user = d
        wm = WorkspaceManager(root=tempfile.mkdtemp())
        km = KnowledgeManager()

        md_path = Path(__file__).parent.parent / "resources" / "dotnet-ai-agent-project.md"
        file_id = await km.ingest(db_obj, str(md_path), user.id)
        assert file_id is not None

        results = await km.search(user.id, ".NET AI Agent", top_k=3)
        assert len(results) > 0

        removed = await km.remove_file(db_obj, file_id)
        assert removed is True

        import shutil
        shutil.rmtree(wm.root, ignore_errors=True)

    async def test_ingest_nonexistent(self, db, d):
        db_obj, user = d
        km = KnowledgeManager()
        file_id = await km.ingest(db_obj, "/nonexistent/path.md", user.id)
        assert file_id is None

    async def test_search_empty_user(self, db, d):
        db_obj, user = d
        km = KnowledgeManager()
        results = await km.search(user.id, "anything")
        assert results == []

    async def test_singleton(self):
        km1 = KnowledgeManager()
        km2 = KnowledgeManager()
        assert km1 is km2

    async def test_docx_semantic_kernel(self, db, d):
        """Ingest the real DOCX and search for 'Semantic Kernel' — chunks should be meaningful."""
        db_obj, user = d
        km = KnowledgeManager()
        wm = WorkspaceManager(root=tempfile.mkdtemp())

        docx_path = Path(__file__).parent.parent / "resources" / "dotnet-ai-agent-project.docx"
        file_id = await km.ingest(db_obj, str(docx_path), user.id)
        assert file_id is not None, "ingest should succeed"

        results = await km.search(user.id, "Semantic Kernel", top_k=3)
        assert len(results) > 0, "should find chunks about Semantic Kernel"

        for r in results:
            print(f"\n  score={r['score']:.4f}  [{len(r['chunk'])} chars]")
            print(f"  {r['chunk'][:300]}...")

        # At least one chunk should mention Semantic Kernel
        found = any("Semantic Kernel" in r["chunk"] for r in results)
        assert found, f"search results must contain 'Semantic Kernel'"

        # Content should be meaningful — not just "Semantic Kernel" alone in a table cell
        for r in results:
            c = r["chunk"]
            # Should have substantial content (not just a single line)
            lines = [l for l in c.splitlines() if l.strip() and not l.strip().startswith("|")]
            text_body = " ".join(lines)
            assert len(text_body) > 30, f"chunk too short ({len(text_body)} chars): {c[:100]}"

        await km.remove_file(db_obj, file_id)
        import shutil
        shutil.rmtree(wm.root, ignore_errors=True)
