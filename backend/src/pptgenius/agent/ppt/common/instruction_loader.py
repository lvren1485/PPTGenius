"""Instruction file loader — reads .json instruction files and injects them
into agent prompts.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pptgenius.infrastructure.config import RESOURCES_DIR

_INSTRUCTIONS_DIR = RESOURCES_DIR / "instructions"


@lru_cache(maxsize=1)
def _get_how_to_read() -> str:
    path = _INSTRUCTIONS_DIR / "HOW_TO_READ.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


@lru_cache(maxsize=1)
def _load_json(filename: str) -> dict:
    path = _INSTRUCTIONS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Instruction file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_how_to_read() -> str:
    return _get_how_to_read()


def get_instruction(filename: str) -> dict:
    return _load_json(filename)


def get_shared_instructions(*filenames: str) -> str:
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


def get_full_instruction_context() -> str:
    """HOW_TO_READ + all core instruction files + shared.  ~8k tokens."""
    parts = [get_how_to_read(), ""]

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

    parts.append("### Chart Instructions")
    for c in list_chart_instructions():
        parts.append(f"- `{c['chart_type']}` → {c['file']}: {c['description'][:100]}")
    parts.append("")

    parts.append(get_shared_instructions("position", "font", "fill", "line"))
    return "\n".join(parts)


def list_chart_instructions() -> list[dict[str, str]]:
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
