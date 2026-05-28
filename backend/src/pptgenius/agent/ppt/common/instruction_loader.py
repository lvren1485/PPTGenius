"""Instruction file loader — reads .json instruction files and injects them
into agent prompts.  All agents (Text/Chart/Shape/Freedom) use this to stay
current with the instruction schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from pptgenius.infrastructure.config import RESOURCES_DIR

_INSTRUCTIONS_DIR = RESOURCES_DIR / "instructions"

_CACHE: dict[str, dict] = {}


def _load_json(filename: str) -> dict:
    """Load a single instruction JSON file (cached)."""
    if filename in _CACHE:
        return _CACHE[filename]
    path = _INSTRUCTIONS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Instruction file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    _CACHE[filename] = data
    return data


def get_instruction(filename: str) -> dict:
    """Load an instruction file by relative path from instructions/.

    Example: get_instruction("textbox.json"), get_instruction("chart/column.json")
    """
    return _load_json(filename)


def get_shared_instructions(*filenames: str) -> str:
    """Load and format shared/*.json instructions as a concatenated prompt block.

    Example: get_shared_instructions("position", "font") →
        "## 元素位置定义\n{position.json content}\n\n## 字体样式定义\n{font.json content}"
    """
    parts = []
    for name in filenames:
        data = _load_json(f"shared/{name}.json")
        desc = data.get("_description", data.get("description", name))
        if isinstance(desc, list):
            desc = " ".join(desc)
        parts.append(f"### {desc}")
        parts.append("```json")
        parts.append(json.dumps(data, ensure_ascii=False, indent=2))
        parts.append("```")
    return "\n\n".join(parts)


def list_chart_instructions() -> list[dict[str, str]]:
    """List all chart instruction files with their chart_type and description."""
    chart_dir = _INSTRUCTIONS_DIR / "chart"
    results = []
    for f in sorted(chart_dir.glob("*.json")):
        data = _load_json(f"chart/{f.name}")
        desc = data.get("description", "")
        if isinstance(desc, list):
            desc = " ".join(desc)
        results.append({
            "file": f"chart/{f.name}",
            "chart_type": data.get("chart_type", ""),
            "description": desc,
        })
    return results
