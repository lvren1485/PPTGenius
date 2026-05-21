"""Tests for tool registry and basic tool execution."""

import agent.agents.tools  # noqa: F401 - trigger registration
from agent.agents.tools import list_tools, execute_tool


def test_tools_registered():
    tools = list_tools()
    assert len(tools) >= 10
    names = [t["name"] for t in tools]
    assert "create_plan" in names
    assert "query_knowledge_base" in names
    assert "generate_ppt" in names
    assert "search_web" in names
    assert "select_template" in names


def test_select_template():
    result = execute_tool("select_template", preference="corporate")
    assert "template_name" in result
    assert result["template_name"] == "professional-blue"


def test_list_templates():
    result = execute_tool("list_templates")
    assert "templates" in result
    assert len(result["templates"]) >= 3


def test_generate_table():
    result = execute_tool("generate_table",
                          headers=["Name", "Value"],
                          rows=[["A", "1"], ["B", "2"]])
    assert result["row_count"] == 2
    assert result["col_count"] == 2


def test_unknown_tool():
    result = execute_tool("nonexistent")
    assert "error" in result


def test_query_database_invalid_sql():
    result = execute_tool("query_database", sql="INVALID SQL")
    assert "error" in result or "columns" in result
