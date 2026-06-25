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
    """
    Populates the database with default application roles.

    Creates specified roles if they do not already exist, and associates any existing
    users matching the provided administrator email addresses with the 'admin' role.
    """
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
    Seeds the database with platform-wide default templates.

    Inserts predefined templates that are not currently present,
    removes deprecated templates, and updates existing templates to match
    the current template definitions and layouts.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PlatformTemplate))
        existing: dict[str, PlatformTemplate] = {
            template.title: template for template in result.scalars().all()
        }

        # Legacy platform template titles that are no longer part of the seed
        legacy_titles = {
            "Web3 Summit",
            "Dev Hackathon",
            "Builder Blitz",
            "Founder's Circle",
            "Men's Summit 2026",
            "Harvesta 2026",
            "Reddit Summit",
            "Reddit Summit Badge",
            "Community Connect",
            "Open Source Day",
            "Bootcamp Badge",
            "Graduate Cohort",
            "Next Gen Meetup",
            "Meetup Connect",
            "Spark Support",
            "Meet Our Speaker",
            "Keynote Speaker",
            "Achieveher",
            "Dev Summit",
            "Men's Summit",
            "Next Gen",
        }

        deleted = 0
        for title in list(existing.keys()):
            if title in legacy_titles:
                await session.delete(existing[title])
                existing.pop(title)
                deleted += 1

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
        if deleted > 0:
            logger.info("Deleted %d legacy platform templates.", deleted)

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
    """
    Runs the database seeding process for default roles and platform templates.

    Configures logging and calls the individual seeders sequentially.
    """
    logging.basicConfig(level=logging.INFO)
    await seed_roles()
    await seed_platform_templates()
