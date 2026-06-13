"""Database seed script — idempotent, only inserts when tables are empty.

Runs at startup after create_all().  Import this from engine.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from .models import Style

logger = logging.getLogger("pptgenius.db.seed")

_RESOURCES = Path(__file__).resolve().parent.parent.parent / "resources"
_COLOR_SCHEMES_DIR = _RESOURCES / "color_schemes"


async def seed(engine: AsyncEngine) -> None:
    """Seed styles table.  Idempotent — skips if data exists."""
    import sqlalchemy as sa

    async with engine.begin() as conn:
        result = await conn.execute(select(func.count()).select_from(Style))
        if result.scalar() == 0:
            if _COLOR_SCHEMES_DIR.exists():
                count = 0
                for f in sorted(_COLOR_SCHEMES_DIR.glob("*.json")):
                    d = json.loads(f.read_text(encoding="utf-8"))
                    await conn.execute(
                        sa.insert(Style).values(
                            name=d["name"],
                            label=d["label"],
                            colors_json=d.get("colors", {}),
                            chart_colors_json=d.get("chart_colors", []),
                            fonts_json=d.get("fonts", {}),
                            style_density=d.get("style_density", "moderate"),
                            decoration_json=d.get("decoration", {}),
                            background_json=d.get("background_json"),
                        )
                    )
                    count += 1
                logger.info("Seeded %d style(s)", count)
        else:
            logger.debug("styles already populated, skipping seed")
