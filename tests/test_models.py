"""Tests for data models."""

import json
from agent.models.outline import SlideOutline, PresentationOutline, TodoItem, Plan


def test_slide_outline_defaults():
    s = SlideOutline(title="Test", bullets=["a", "b"])
    assert s.title == "Test"
    assert s.subtitle is None
    assert len(s.bullets) == 2
    assert s.layout_type == "content"


def test_presentation_outline():
    p = PresentationOutline(
        topic="AI",
        slides=[
            SlideOutline(title="Intro", layout_type="title"),
            SlideOutline(title="Body", bullets=["point 1"]),
        ],
    )
    assert p.topic == "AI"
    assert len(p.slides) == 2
    assert p.slides[0].layout_type == "title"


def test_todo_item():
    t = TodoItem(id=1, description="Search web", tools_needed=["search_web"])
    assert t.status == "pending"
    assert t.depends_on == []


def test_plan():
    p = Plan(
        goal="Make a PPT",
        items=[TodoItem(id=1, description="Research")],
    )
    assert p.goal == "Make a PPT"
    assert len(p.items) == 1
    assert p.revised_at is None


def test_plan_serialization():
    p = Plan(
        goal="Test",
        items=[TodoItem(id=1, description="Step 1")],
    )
    data = p.model_dump()
    assert data["goal"] == "Test"
    assert data["items"][0]["description"] == "Step 1"
