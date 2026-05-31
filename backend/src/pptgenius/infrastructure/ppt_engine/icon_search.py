"""Tabler Icon search & color replacement for PPT decoration.

Uses ~5,000 MIT-licensed Tabler outline icons bundled in resources/tabler/.
LLM searches by tag/category/name → picks one by name → engine applies color.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ppt_engine.icon")

_ICONS_META: Optional[dict] = None
_ICONS_DIR: Optional[Path] = None


def _get_icons_dir() -> Path:
    global _ICONS_DIR
    if _ICONS_DIR is None:
        _ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "tabler" / "svg"
    return _ICONS_DIR


def _load_meta() -> dict:
    global _ICONS_META
    if _ICONS_META is not None:
        return _ICONS_META
    meta_path = (
        Path(__file__).resolve().parent.parent.parent / "resources" / "tabler" / "icons_meta.json"
    )
    if not meta_path.exists():
        logger.warning("icons_meta.json not found at %s", meta_path)
        _ICONS_META = {}
        return _ICONS_META
    with open(meta_path, "r", encoding="utf-8") as f:
        _ICONS_META = json.load(f)
    return _ICONS_META


def search_icons(query: str, top_k: int = 5) -> list[dict]:
    """Search Tabler icons by tag / category / name. Returns top-k matches."""
    icons = _load_meta()
    if not icons:
        return []

    query_lower = query.lower()
    query_words = query_lower.split()
    scored: list[dict] = []

    for name, meta in icons.items():
        tags = [str(t).lower() for t in meta.get("tags", [])]
        category = str(meta.get("category", "")).lower()
        score = 0

        # tag matches
        for tag in tags:
            if query_lower in tag:
                score += 10
            elif any(w in tag for w in query_words):
                score += 5
            else:
                for tw in tag.split():
                    if any(qw in tw for qw in query_words):
                        score += 3
                        break

        # category match
        if query_lower in category:
            score += 3

        # name match
        name_lower = name.lower()
        if name_lower == query_lower:
            score += 15  # exact name match — strong signal
        elif query_lower in name_lower:
            score += 3

        if score > 0:
            scored.append({
                "name": name,
                "category": meta.get("category", ""),
                "tags": meta.get("tags", []),
                "score": score,
            })

    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def get_colored_svg(icon_name: str, color: str, workspace: str) -> str:
    """Load an outline icon SVG, replace its stroke color, save to a temp dir.

    Returns the path relative to *workspace* so image_parser can resolve it.
    """
    svg_path = _get_icons_dir() / f"{icon_name}.svg"
    if not svg_path.exists():
        raise FileNotFoundError(f"Icon not found: {icon_name}")

    with open(svg_path, "r", encoding="utf-8") as f:
        svg_text = f.read()

    hex_color = color.lstrip("#") if color.startswith("#") else color

    # Replace stroke="currentColor" (Tabler uses this on the root <svg> element)
    # Only replace the first occurrence — the root element's stroke attribute
    svg_text = svg_text.replace('stroke="currentColor"', f'stroke="#{hex_color}"', 1)

    temp_dir = Path(workspace) / ".temp_icons"
    temp_dir.mkdir(parents=True, exist_ok=True)

    out_name = f"{icon_name}_{hex_color}.svg"
    out_path = temp_dir / out_name
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg_text)

    logger.debug("colored SVG saved: %s", out_path)
    return os.path.relpath(str(out_path), workspace)


def cleanup_temp_icons(workspace: str | None) -> None:
    """Remove the .temp_icons directory after PPT generation."""
    if workspace is None:
        return
    temp_dir = Path(workspace) / ".temp_icons"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        logger.debug("cleaned up temp icons: %s", temp_dir)
