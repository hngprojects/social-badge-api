#!/usr/bin/env python3
"""Seed platform_templates with sample layout data for local testing.

Usage:
    uv run python scripts/seed_layouts.py
"""

import asyncio
import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.templates import PlatformTemplate

logger = logging.getLogger(__name__)

TEMPLATES = [
    {
        "title": "Classic",
        "description": (
            "A clean, minimal badge with name and title on a white background."
        ),
        "thumbnail_url": "https://placehold.co/400x200?text=Classic",
        "canvas_data": {"background": "#ffffff", "font": "Inter"},
        "is_active": True,
    },
    {
        "title": "Bold Dark",
        "description": "High-contrast dark badge with vibrant accent colours.",
        "thumbnail_url": "https://placehold.co/400x200?text=Bold+Dark",
        "canvas_data": {"background": "#1a1a1a", "font": "Poppins"},
        "is_active": True,
    },
    {
        "title": "Gradient",
        "description": "Modern gradient background with smooth colour transitions.",
        "thumbnail_url": "https://placehold.co/400x200?text=Gradient",
        "canvas_data": {
            "background": "linear-gradient(135deg, #667eea, #764ba2)",
            "font": "Inter",
        },
        "is_active": True,
    },
    {
        "title": "Corporate",
        "description": (
            "Professional layout suited for enterprise and conference badges."
        ),
        "thumbnail_url": "https://placehold.co/400x200?text=Corporate",
        "canvas_data": {"background": "#f5f5f5", "font": "Georgia"},
        "is_active": True,
    },
    {
        "title": "Retro",
        "description": "Vintage-style badge with warm tones and serif typography.",
        "thumbnail_url": "https://placehold.co/400x200?text=Retro",
        "canvas_data": {"background": "#f5e6c8", "font": "Courier"},
        "is_active": False,
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PlatformTemplate))
        await session.commit()

        templates = [PlatformTemplate(**template) for template in TEMPLATES]
        session.add_all(templates)
        await session.commit()

        result = await session.execute(
            select(PlatformTemplate).order_by(PlatformTemplate.title)
        )
        seeded = result.scalars().all()

        logger.info("\nSeeded %s platform templates:\n", len(seeded))
        for template in seeded:
            status = "active  " if template.is_active else "inactive"
            logger.info(
                "  [%s]  %-15s  %s",
                status,
                template.title,
                template.description[:50],
            )
        logger.info("")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(seed())
