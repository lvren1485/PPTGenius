"""Database seed script — idempotent, only inserts when tables are empty.

Runs at startup after create_all().  Import this from engine.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from .models import ColorScheme, Template

logger = logging.getLogger("pptgenius.db.seed")

_RESOURCES = Path(__file__).resolve().parent.parent.parent / "resources"
_COLOR_SCHEMES_DIR = _RESOURCES / "color_schemes"
_LAYOUTS_DIR = _RESOURCES / "layouts"


async def seed(engine: AsyncEngine) -> None:
    """Seed color_schemes and templates tables.  Idempotent — skips if data exists."""
    import sqlalchemy as sa

    async with engine.begin() as conn:
        # ── color_schemes ──
        result = await conn.execute(select(func.count()).select_from(ColorScheme))
        if result.scalar() == 0:
            if _COLOR_SCHEMES_DIR.exists():
                count = 0
                for f in sorted(_COLOR_SCHEMES_DIR.glob("*.json")):
                    d = json.loads(f.read_text(encoding="utf-8"))
                    await conn.execute(
                        sa.insert(ColorScheme).values(
                            name=d["name"],
                            label=d["label"],
                            colors_json=d.get("colors", {}),
                            chart_colors_json=d.get("chart_colors", []),
                            fonts_json=d.get("fonts", {}),
                            style_density=d.get("style_density", "moderate"),
                            decoration_json=d.get("decoration", {}),
                        )
                    )
                    count += 1
                logger.info("Seeded %d color scheme(s)", count)
        else:
            logger.debug("color_schemes already populated, skipping seed")

        # ── templates (layouts) ──
        result = await conn.execute(select(func.count()).select_from(Template))
        if result.scalar() == 0:
            if _LAYOUTS_DIR.exists():
                layouts = {}
                for f in sorted(_LAYOUTS_DIR.glob("*.json")):
                    d = json.loads(f.read_text(encoding="utf-8"))
                    layouts[d["name"]] = d

                await conn.execute(
                    sa.insert(Template).values(
                        name="default",
                        label="默认模板",
                        category="general",
                        description="7 种页面布局",
                        layouts_json=layouts,
                    )
                )
                logger.info("Seeded 1 template with %d layout(s)", len(layouts))
        else:
            logger.debug("templates already populated, skipping seed")
