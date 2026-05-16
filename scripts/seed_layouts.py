#!/usr/bin/env python3
"""Seed platform_templates with sample layout data for local testing.

Usage:
    uv run python scripts/seed_layouts.py
"""

import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import delete, select
from app.db.session import AsyncSessionLocal
from app.models.templates import PlatformTemplate


TEMPLATES = [
    {
        "title": "Classic",
        "description": "A clean, minimal badge with name and title on a white background.",
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
        "canvas_data": {"background": "linear-gradient(135deg, #667eea, #764ba2)", "font": "Inter"},
        "is_active": True,
    },
    {
        "title": "Corporate",
        "description": "Professional layout suited for enterprise and conference badges.",
        "thumbnail_url": "https://placehold.co/400x200?text=Corporate",
        "canvas_data": {"background": "#f5f5f5", "font": "Georgia"},
        "is_active": True,
    },
    {
        "title": "Retro",
        "description": "Vintage-style badge with warm tones and serif typography.",
        "thumbnail_url": "https://placehold.co/400x200?text=Retro",
        "canvas_data": {"background": "#f5e6c8", "font": "Courier"},
        "is_active": False,  # inactive — tests that filter works
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PlatformTemplate))
        await session.commit()

        templates = [PlatformTemplate(**t) for t in TEMPLATES]
        session.add_all(templates)
        await session.commit()

        result = await session.execute(
            select(PlatformTemplate).order_by(PlatformTemplate.name)
        )
        seeded = result.scalars().all()

        print(f"\nSeeded {len(seeded)} platform templates:\n")
        for t in seeded:
            status = "active  " if t.is_active else "inactive"
            print(f"  [{status}]  {t.name:<15}  {t.description[:50]}")
        print()


if __name__ == "__main__":
    asyncio.run(seed())
    