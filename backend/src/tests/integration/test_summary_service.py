"""Tests for SummaryService — file upload + web summary with token counting."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest_asyncio

from pptgenius.infrastructure.db.database import Database
from pptgenius.infrastructure.rag.knowledge import KnowledgeService
from pptgenius.infrastructure.rag.summary import SummaryService, summary_service
from pptgenius.infrastructure.rag.web_search import web_search_service


class TestSummaryService:
    @pytest_asyncio.fixture
    async def d(self, db):
        u = await Database(db).create_user("summary_user")
        conv = await Database(db).create_conversation(u.id)
        return Database(db), u, conv

    async def test_summarize_file_document(self, d):
        """Upload a Chinese document and verify LLM summary is stored."""
        db_obj, user, conv = d

        # Create a temp text file with meaningful content
        content = (
            "人工智能技术发展报告\n\n"
            "第一章 概述\n"
            "人工智能（AI）是计算机科学的一个分支，旨在创建能够模拟人类智能的系统。"
            "近年来，深度学习技术的突破使得AI在图像识别、自然语言处理等领域取得了显著进展。\n\n"
            "第二章 大语言模型\n"
            "大语言模型（LLM）基于Transformer架构，通过海量文本数据的预训练，"
            "展现出强大的语言理解和生成能力。代表模型包括GPT-4、Claude、DeepSeek等。"
            "这些模型在问答、翻译、代码生成等任务上表现优异。\n\n"
            "第三章 应用场景\n"
            "AI技术已广泛应用于医疗诊断、金融风控、自动驾驶、智能客服等领域。"
            "企业通过部署AI解决方案，显著提升了运营效率和决策质量。\n\n"
            "第四章 挑战与展望\n"
            "尽管AI发展迅猛，仍面临数据隐私、算法偏见、算力成本等挑战。"
            "未来，可解释AI、联邦学习、绿色计算等方向将成为研究热点。"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            km = KnowledgeService()
            file_id = await km.ingest(db_obj, tmp_path, user.id, conv.id)
            assert file_id is not None, "ingest should succeed"

            kf = await db_obj.get_knowledge_file(file_id)
            assert kf is not None
            assert kf.file_type == "txt"

            # Run summary
            svc = SummaryService()
            result = await svc.summarize_file(db_obj, file_id)

            # Verify result structure
            assert "summary" in result
            assert isinstance(result["summary"], str)
            assert len(result["summary"]) > 20  # meaningful summary
            assert len(result["summary"]) < 1000  # not too long
            assert "token_cost_json" in result
            assert "estimated_cost_cny" in result
            assert result["estimated_cost_cny"] >= 0
            tc = result["token_cost_json"]
            assert tc["input_tokens"] > 0  # must have consumed tokens
            assert tc["output_tokens"] > 0

            # Verify DB persistence
            kf = await db_obj.get_knowledge_file(file_id)
            assert kf.summary_json is not None
            assert len(kf.summary_json) > 20
            assert "AI" in kf.summary_json or "人工智能" in kf.summary_json

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def test_summarize_file_short_data_csv(self, d):
        """Data file with ≤30 rows should skip summary."""
        db_obj, user, conv = d

        content = "name,value\n" + "\n".join(f"item{i},{i*10}" for i in range(5))
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            km = KnowledgeService()
            file_id = await km.ingest(db_obj, tmp_path, user.id, conv.id)
            assert file_id is not None

            svc = SummaryService()
            result = await svc.summarize_file(db_obj, file_id)

            # ≤30 rows → skip, no LLM cost
            assert result["summary"] is None
            assert result["token_cost_json"]["total_tokens"] == 0
            assert result["estimated_cost_cny"] == 0.0

            kf = await db_obj.get_knowledge_file(file_id)
            assert kf.summary_json is None

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def test_summarize_file_data_file(self, d):
        """Data files (csv/xlsx) should skip summary — parser handles it."""
        db_obj, user, conv = d

        content = "name,value\n" + "\n".join(f"item{i},{i*10}" for i in range(50))
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name

        try:
            km = KnowledgeService()
            file_id = await km.ingest(db_obj, tmp_path, user.id, conv.id)
            assert file_id is not None

            svc = SummaryService()
            result = await svc.summarize_file(db_obj, file_id)

            # Data file → parser already structured, skip LLM summary
            assert result["summary"] is None
            assert result["token_cost_json"]["total_tokens"] == 0
            assert result["estimated_cost_cny"] == 0.0

            kf = await db_obj.get_knowledge_file(file_id)
            assert kf.summary_json is None

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def test_summarize_web(self, d):
        """Web summary should write summary_json + web_url."""
        db_obj, user, conv = d

        # Simulate web content (without actually fetching)
        web_text = (
            "Python 3.13 发布说明\n\n"
            "Python 3.13 于 2024 年 10 月正式发布。"
            "此版本引入了实验性的无 GIL 模式，允许 CPython 在多核 CPU 上实现真正的并行执行。"
            "此外，新的 JIT 编译器基于 copy-and-patch 技术，提供了显著的性能提升。"
            "类型系统也得到了增强，包括 TypedDict 的改进和新的类型别名语法。"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(web_text)
            tmp_path = f.name

        try:
            km = KnowledgeService()
            file_id = await km.ingest(db_obj, tmp_path, user.id, conv.id)
            assert file_id is not None

            svc = SummaryService()
            result = await svc.summarize_web(
                db_obj, file_id,
                title="Python 3.13 Release Notes",
                url="https://example.com/python313",
                text=web_text,
            )

            assert "summary" in result
            assert len(result["summary"]) > 20
            assert result["estimated_cost_cny"] >= 0
            assert result["token_cost_json"]["input_tokens"] > 0

            kf = await db_obj.get_knowledge_file(file_id)
            assert kf.summary_json is not None
            assert kf.web_url == "https://example.com/python313"

        finally:
            Path(tmp_path).unlink(missing_ok=True)
