"""Tool registry - maps tool names to callable functions.

Each tool function accepts JSON-serializable kwargs and returns a dict.
"""

from typing import Any, Callable

TOOL_REGISTRY: dict[str, Callable] = {}


def register(func: Callable) -> Callable:
    """Decorator: register a function as a tool."""
    name = func.__name__
    TOOL_REGISTRY[name] = func
    return func


def execute_tool(name: str, **kwargs) -> dict[str, Any]:
    """Execute a tool by name with the given kwargs.

    Returns the tool's output dict.
    If the tool is not found or errors, returns an error dict.
    """
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}"}
    try:
        result = TOOL_REGISTRY[name](**kwargs)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as e:
        return {"error": str(e)}


def list_tools() -> list[dict]:
    """List all registered tools with their docstrings."""
    return [
        {"name": name, "description": fn.__doc__ or ""}
        for name, fn in sorted(TOOL_REGISTRY.items())
    ]
