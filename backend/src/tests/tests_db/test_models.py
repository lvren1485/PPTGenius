"""Static tests for Phase 0 schema changes — model definitions, tablenames, new columns."""

import pytest

from pptgenius.infrastructure.db.models import (
    Conversation,
    KnowledgeFile,
    Message,
    Outline,
    OutlineSection,
    OutlineSlide,
    OutlineSnapshot,
    Presentation,
    PresentationSlide,
    Style,
    User,
)


class TestStyleModel:
    """color_schemes → styles rename + background_json."""

    def test_tablename_is_styles(self):
        assert Style.__tablename__ == "styles"

    def test_has_background_json_column(self):
        assert "background_json" in {c.key for c in Style.__table__.columns}

    def test_has_all_legacy_columns(self):
        cols = {c.key for c in Style.__table__.columns}
        for name in ("name", "label", "colors_json", "chart_colors_json",
                     "fonts_json", "style_density", "decoration_json", "is_active"):
            assert name in cols

    def test_no_template_table_exists(self):
        """Template model should not exist after deletion."""
        from pptgenius.infrastructure.db import models
        assert not hasattr(models, "Template")


class TestConversationModel:
    def test_has_current_outline_id(self):
        cols = {c.key for c in Conversation.__table__.columns}
        assert "current_outline_id" in cols

    def test_current_outline_id_nullable(self):
        col = Conversation.__table__.columns["current_outline_id"]
        assert col.nullable is True


class TestOutlineModel:
    """Outlines: version → version_major/minor/patch + new columns."""

    def test_semantic_version_columns(self):
        cols = {c.key for c in Outline.__table__.columns}
        assert "version_major" in cols
        assert "version_minor" in cols
        assert "version_patch" in cols

    def test_version_defaults(self):
        for name in ("version_major", "version_minor", "version_patch"):
            col = Outline.__table__.columns[name]
            assert col.default is not None

    def test_new_columns(self):
        cols = {c.key for c in Outline.__table__.columns}
        for name in ("eval_detail",):
            assert name in cols, f"missing column: {name}"

    def test_old_version_column_removed(self):
        cols = {c.key for c in Outline.__table__.columns}
        assert "version" not in cols

    def test_has_sections_relationship(self):
        assert hasattr(Outline, "sections")


class TestOutlineSectionModel:
    def test_tablename(self):
        assert OutlineSection.__tablename__ == "outline_sections"

    def test_required_columns(self):
        cols = {c.key for c in OutlineSection.__table__.columns}
        for name in ("id", "outline_id", "section_index", "title",
                     "description", "slide_count", "created_at"):
            assert name in cols, f"missing: {name}"

    def test_has_slides_relationship(self):
        assert hasattr(OutlineSection, "slides")

    def test_has_outline_relationship(self):
        assert hasattr(OutlineSection, "outline")


class TestOutlineSlideModel:
    def test_section_id_column(self):
        cols = {c.key for c in OutlineSlide.__table__.columns}
        assert "section_id" in cols

    def test_citations_and_status(self):
        cols = {c.key for c in OutlineSlide.__table__.columns}
        for name in ("citations", "status"):
            assert name in cols

    def test_no_agent_id(self):
        cols = {c.key for c in OutlineSlide.__table__.columns}
        assert "agent_id" not in cols

    def test_status_default_pending(self):
        col = OutlineSlide.__table__.columns["status"]
        assert col.default is not None


class TestOutlineSnapshotModel:
    def test_tablename(self):
        assert OutlineSnapshot.__tablename__ == "outline_snapshots"

    def test_required_columns(self):
        cols = {c.key for c in OutlineSnapshot.__table__.columns}
        for name in ("id", "outline_id", "user_id", "conversation_id",
                     "version", "outline_json", "created_at"):
            assert name in cols


class TestPresentationModel:
    def test_uses_style_id(self):
        cols = {c.key for c in Presentation.__table__.columns}
        assert "style_id" in cols
        assert "template_id" not in cols
        assert "color_scheme_id" not in cols

    def test_no_agent_id(self):
        cols = {c.key for c in Presentation.__table__.columns}
        assert "agent_id" not in cols


class TestPresentationSlideModel:
    def test_uses_style_id(self):
        cols = {c.key for c in PresentationSlide.__table__.columns}
        assert "style_id" in cols
        assert "template_id" not in cols
        assert "color_scheme_id" not in cols

    def test_no_agent_id(self):
        cols = {c.key for c in PresentationSlide.__table__.columns}
        assert "agent_id" not in cols


class TestKnowledgeFileModel:
    def test_new_columns(self):
        cols = {c.key for c in KnowledgeFile.__table__.columns}
        for name in ("conversation_id", "web_url", "summary_json"):
            assert name in cols

    def test_conversation_id_nullable(self):
        col = KnowledgeFile.__table__.columns["conversation_id"]
        assert col.nullable is True

    def test_web_url_length(self):
        col = KnowledgeFile.__table__.columns["web_url"]
        assert col.type.length == 2048


class TestMessageModel:
    def test_has_token_cost_json(self):
        cols = {c.key for c in Message.__table__.columns}
        assert "token_cost_json" in cols

    def test_estimated_cost_still_exists(self):
        cols = {c.key for c in Message.__table__.columns}
        assert "estimated_cost" in cols


class TestUserModel:
    def test_basic_columns(self):
        cols = {c.key for c in User.__table__.columns}
        for name in ("id", "name", "password", "other", "created_at"):
            assert name in cols
