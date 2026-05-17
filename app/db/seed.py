"""Seed script for reference data.

Run with: uv run python -m app.db.seed
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import PlatformTemplate

logger = logging.getLogger(__name__)


PLATFORM_TEMPLATES_SEED = [
    {
        "title": "Creative",
        "canvas_data": {"layout": "creative-v1"},
        "thumbnail_url": None,
    },
    {
        "title": "Professional",
        "canvas_data": {"layout": "professional-v1"},
        "thumbnail_url": None,
    },
    {
        "title": "Minimal",
        "canvas_data": {"layout": "minimal-v1"},
        "thumbnail_url": None,
    },
    {
        "title": "Bold",
        "canvas_data": {"layout": "bold-v1"},
        "thumbnail_url": None,
    },
]


async def seed_platform_templates() -> None:
    """Insert platform templates whose titles are not yet present."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PlatformTemplate.title))
        existing_titles = set(result.scalars().all())

        to_insert = [
            data
            for data in PLATFORM_TEMPLATES_SEED
            if data["title"] not in existing_titles
        ]

        if not to_insert:
            logger.info(
                "Platform templates already seeded (%d found).",
                len(existing_titles),
            )
            return

        for data in to_insert:
            session.add(PlatformTemplate(**data))
            
        await session.commit()
        logger.info("Seeded %d platform templates.", len(to_insert))


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await seed_platform_templates()


if __name__ == "__main__":
    asyncio.run(main())