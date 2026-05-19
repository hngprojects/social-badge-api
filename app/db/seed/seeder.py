import logging

from sqlalchemy import select

from app.db.seed.definitions import PLATFORM_TEMPLATES_SEED
from app.db.session import AsyncSessionLocal
from app.models import PlatformTemplate

logger = logging.getLogger(__name__)


async def seed_platform_templates() -> None:
    """
    Insert platform templates whose titles are not yet present.
    Updates canvas_data and category on existing rows so the seed
    stays in sync with the spec without losing existing IDs.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PlatformTemplate))
        existing: dict[str, PlatformTemplate] = {
            template.title: template for template in result.scalars().all()
        }

        inserted = 0
        updated = 0

        for data in PLATFORM_TEMPLATES_SEED:
            if data["title"] in existing:
                row = existing[data["title"]]
                # Sync with the seed definition if fields changed
                changed = False
                if row.canvas_data != data["canvas_data"]:
                    row.canvas_data = data["canvas_data"]
                    changed = True
                if row.category != data["category"]:
                    row.category = data["category"]
                    changed = True
                target_thumb = data["thumbnail_url"]
                if target_thumb is not None and row.thumbnail_url != target_thumb:
                    row.thumbnail_url = target_thumb
                    changed = True
                if changed:
                    updated += 1
            else:
                session.add(
                    PlatformTemplate(
                        title=data["title"],
                        category=data["category"],
                        canvas_data=data["canvas_data"],
                        thumbnail_url=data["thumbnail_url"],
                    )
                )
                inserted += 1

        await session.commit()
        if inserted == 0 and updated == 0:
            logger.info(
                "Platform templates already seeded (%d found).",
                len(existing),
            )
        elif inserted == 0:
            logger.info("Updated %d existing platform templates.", updated)
        else:
            logger.info(
                "Seeded %d platform templates (updated %d existing).",
                inserted,
                updated,
            )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await seed_platform_templates()
