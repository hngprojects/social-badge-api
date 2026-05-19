import logging

from sqlalchemy import select

from app.db.seed.definitions import (
    ADMIN_SEED_EMAILS,
    PLATFORM_TEMPLATES_SEED,
    ROLE_SEED,
)
from app.db.session import AsyncSessionLocal
from app.models import PlatformTemplate, Role, User, UserRole

logger = logging.getLogger(__name__)


async def seed_roles(admin_emails: list[str] | None = None) -> None:
    if admin_emails is None:
        admin_emails = ADMIN_SEED_EMAILS

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Role))
        existing: dict[str, Role] = {role.name: role for role in result.scalars().all()}

        inserted = 0
        for role_name in ROLE_SEED:
            if role_name not in existing:
                role = Role(name=role_name)
                session.add(role)
                existing[role_name] = role
                inserted += 1

        await session.flush()

        if inserted == 0:
            logger.info("Roles already seeded (%d found).", len(existing))
        else:
            logger.info("Seeded %d roles.", inserted)

        admin_role = existing.get("admin")
        if admin_role is None:
            await session.commit()
            return

        if not admin_emails:
            await session.commit()
            return

        result = await session.execute(select(User).where(User.email.in_(admin_emails)))
        users = result.scalars().all()
        if not users:
            await session.commit()
            logger.info("No admin users found for seeded emails.")
            return

        user_ids = [user.id for user in users]
        existing_links_result = await session.execute(
            select(UserRole.user_id).where(
                UserRole.role_id == admin_role.id,
                UserRole.user_id.in_(user_ids),
            )
        )
        existing_user_ids = set(existing_links_result.scalars().all())

        assigned = 0
        for user in users:
            if user.id in existing_user_ids:
                continue
            session.add(UserRole(user_id=user.id, role_id=admin_role.id))
            assigned += 1

        await session.commit()
        if assigned == 0:
            logger.info("Admin roles already assigned for seeded users.")
        else:
            logger.info("Assigned admin role to %d users.", assigned)


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
    await seed_roles()
    await seed_platform_templates()
