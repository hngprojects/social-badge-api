import logging

from sqlalchemy import select

from app.db.seed import PLATFORM_TEMPLATES_SEED
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
                # Keep canvas_data and category in sync with the seed definition
                row.canvas_data = data["canvas_data"]
                row.category = data["category"]
                if data["thumbnail_url"] is not None:
                    row.thumbnail_url = data["thumbnail_url"]
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
        if inserted == 0:
            logger.info(
                "Platform templates already seeded (%d found).",
                len(existing),
            )
        else:
            logger.info("Seeded %d platform templates.", inserted)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await seed_platform_templates()
