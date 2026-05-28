"""Instruction file loader — reads .json instruction files and injects them
into agent prompts.  All agents (Text/Chart/Shape/Freedom) use this to stay
current with the instruction schema.

Also loads HOW_TO_READ.md — the notation guide that explains type conventions
(string|null, hex[], alignment, etc.) used in all instruction files.
"""

from __future__ import annotations

import json
from pathlib import Path

from pptgenius.infrastructure.config import RESOURCES_DIR

_INSTRUCTIONS_DIR = RESOURCES_DIR / "instructions"

_CACHE: dict[str, dict] = {}
_HOW_TO_READ: str | None = None


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


def get_how_to_read() -> str:
    """Load HOW_TO_READ.md — the notation guide for reading instruction files.

    This explains type conventions (string|null, hex[], int 0-8, etc.),
    the field notation format, and common mistakes.  Include this at the
    beginning of every agent's instruction context so the LLM correctly
    interprets the instruction JSON schemas.
    """
    global _HOW_TO_READ
    if _HOW_TO_READ is not None:
        return _HOW_TO_READ
    path = _INSTRUCTIONS_DIR / "HOW_TO_READ.md"
    if not path.exists():
        _HOW_TO_READ = ""
        return ""
    _HOW_TO_READ = path.read_text(encoding="utf-8")
    return _HOW_TO_READ


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


def get_instruction_context(*instruction_files: str) -> str:
    """Build a complete instruction context block for an agent.

    Includes HOW_TO_READ.md (notation guide) followed by the requested
    instruction files.  Use this as the base of every sub-agent's system prompt.

    Example:
        get_instruction_context("textbox.json", "table.json")
    """
    parts = [get_how_to_read(), ""]
    for fname in instruction_files:
        data = get_instruction(fname)
        parts.append(f"## {fname}")
        parts.append("```json")
        parts.append(json.dumps(data, ensure_ascii=False, indent=2))
        parts.append("```")
        parts.append("")
    return "\n".join(parts)


def get_full_instruction_context() -> str:
    """Return HOW_TO_READ.md + summaries of ALL instruction files.

    Used by FreedomAgent to get complete knowledge without reading every file.
    """
    parts = [get_how_to_read(), ""]

    # Core element instructions
    for fname in ("textbox.json", "table.json", "picture.json",
                   "shape.json", "background.json"):
        data = get_instruction(fname)
        desc = data.get("description", "")
        if isinstance(desc, list):
            desc = " ".join(desc)
        parts.append(f"### {fname} — {desc}")
        parts.append("```json")
        parts.append(json.dumps(data, ensure_ascii=False, indent=2))
        parts.append("```")
        parts.append("")

    # Chart instructions summary
    parts.append("### Chart Instructions")
    for c in list_chart_instructions():
        parts.append(f"- `{c['chart_type']}` → {c['file']}: {c['description'][:100]}")
    parts.append("")

    # Shared
    parts.append(get_shared_instructions("position", "font", "fill", "line"))

    return "\n".join(parts)


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
