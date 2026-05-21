import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import (
    CloudinaryUploadError,
    NotTemplateOwnerError,
    OrganiserTemplateNotFoundError,
    PlatformTemplateNotFoundError,
    PublicTemplateNotFoundError,
    TemplateAlreadyPublishedError,
    TemplateInstanceForbiddenError,
    TemplateInstanceNotFoundError,
)
from app.core.slug import generate_share_slug
from app.models import OrganiserTemplate, PlatformTemplate
from app.models.templates import TemplateHashtag
from app.services.cloudinary import (
    delete_asset,
    delete_logo,
    upload_logo,
)

logger = logging.getLogger(__name__)

# Valid gallery categories — used for validation so we can return a clean 400
# rather than an empty list when the client sends a typo.
VALID_CATEGORIES = frozenset(
    {
        "festivals",
        "hackathons",
        "conferences",
        "community",
        "bootcamp",
        "meetups",
        "speakers",
        "trending",
    }
)


async def create_template_instance(
    session: AsyncSession,
    organiser_id: UUID,
    platform_template_id: UUID,
) -> OrganiserTemplate:
    result = await session.execute(
        select(PlatformTemplate).where(PlatformTemplate.id == platform_template_id)
    )
    platform_template = result.scalars().first()
    if platform_template is None:
        raise PlatformTemplateNotFoundError

    instance = OrganiserTemplate(
        organiser_id=organiser_id,
        platform_template_id=platform_template_id,
        title=platform_template.title,
        canvas_data=platform_template.canvas_data or {},
    )
    session.add(instance)
    await session.flush()
    await session.commit()
    await session.refresh(instance)

    logger.info(
        "Created template instance %s for organiser %s",
        instance.id,
        organiser_id,
    )
    return instance


async def publish_template(
    session: AsyncSession,
    organiser_id: UUID,
    template_id: UUID,
) -> OrganiserTemplate:
    result = await session.execute(
        select(OrganiserTemplate).where(OrganiserTemplate.id == template_id)
    )
    template = result.scalars().first()
    if template is None or template.deleted_at is not None:
        raise OrganiserTemplateNotFoundError
    if template.organiser_id != organiser_id:
        raise NotTemplateOwnerError
    if template.is_published:
        raise TemplateAlreadyPublishedError

    now = datetime.now(UTC)
    if template.share_slug is None:
        for _ in range(settings.MAX_SLUG_RETRIES):
            template.is_published = True
            template.published_at = now
            template.share_slug = generate_share_slug()
            try:
                await session.flush()
                break
            except IntegrityError:
                await session.rollback()
                continue
        else:
            raise RuntimeError("Could not generate a unique share slug")

    await session.commit()
    await session.refresh(template)

    logger.info("Published template %s by organiser %s", template.id, organiser_id)
    return template


async def unpublish_template(
    session: AsyncSession,
    organiser_id: UUID,
    template_id: UUID,
) -> OrganiserTemplate:
    result = await session.execute(
        select(OrganiserTemplate).where(OrganiserTemplate.id == template_id)
    )
    template = result.scalars().first()
    if template is None or template.deleted_at is not None:
        raise OrganiserTemplateNotFoundError
    if template.organiser_id != organiser_id:
        raise NotTemplateOwnerError

    template.is_published = False
    template.published_at = None
    await session.commit()
    await session.refresh(template)

    logger.info("Unpublished template %s by organiser %s", template.id, organiser_id)
    return template


async def upload_template_logo(
    session: AsyncSession,
    instance_id: UUID,
    organiser_id: UUID,
    image_data: bytes,
) -> str:
    """Upload a logo for a template instance and return the Cloudinary URL.

    Raises:
        TemplateInstanceNotFoundError: if the instance does not exist.
        TemplateInstanceForbiddenError: if the instance belongs to another organiser.
        CloudinaryUploadError: if the Cloudinary upload fails.
    """
    result = await session.execute(
        select(OrganiserTemplate).where(
            OrganiserTemplate.id == instance_id,
            OrganiserTemplate.deleted_at.is_(None),
        )
    )
    instance = result.scalars().first()

    if instance is None:
        raise TemplateInstanceNotFoundError

    if instance.organiser_id != organiser_id:
        raise TemplateInstanceForbiddenError

    old_public_id = instance.logo_public_id

    # Upload first so the DB always points at a live asset.
    logo_url, public_id = await upload_logo(image_data)

    instance.logo_url = logo_url
    instance.logo_public_id = public_id
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        # DB commit failed — best-effort cleanup of the just-uploaded asset.
        try:
            await delete_logo(public_id)
        except Exception:
            logger.warning(
                "Failed to clean up Cloudinary asset %s after DB commit failure",
                public_id,
            )
        raise
    await session.refresh(instance)

    # Only delete the old asset after the DB is consistent.
    # A failure here is non-fatal — the new logo is already persisted.
    if old_public_id:
        try:
            await delete_logo(old_public_id)
        except Exception:
            logger.warning(
                "Failed to delete old Cloudinary asset %s — manual cleanup may be required",  # noqa: E501
                old_public_id,
            )

    logger.info(
        "Uploaded logo for template instance %s (public_id=%s)",
        instance_id,
        public_id,
    )
    return logo_url


async def get_public_template_by_slug(
    session: AsyncSession,
    slug: str,
) -> OrganiserTemplate:
    result = await session.execute(
        select(OrganiserTemplate)
        .options(selectinload(OrganiserTemplate.hashtags))
        .where(
            OrganiserTemplate.share_slug == slug,
            OrganiserTemplate.is_published.is_(True),
            OrganiserTemplate.deleted_at.is_(None),
        )
    )
    template = result.scalars().first()
    if template is None:
        raise PublicTemplateNotFoundError

    logger.info("Public lookup for slug %s resolved to template %s", slug, template.id)
    return template


async def list_platform_templates(
    session: AsyncSession,
    category: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> tuple[list[PlatformTemplate], int]:
    if category is not None:
        normalised = category.strip().lower()
        if normalised not in VALID_CATEGORIES:
            raise ValueError(
                f"Unknown category '{category}'. "
                f"Valid options: {', '.join(sorted(VALID_CATEGORIES))}"
            )
        count_stmt = select(func.count(PlatformTemplate.id)).where(
            PlatformTemplate.is_active.is_(True),
            PlatformTemplate.category == normalised,
        )
        stmt = (
            select(PlatformTemplate)
            .where(
                PlatformTemplate.is_active.is_(True),
                PlatformTemplate.category == normalised,
            )
            .order_by(PlatformTemplate.title)
        )
    else:
        count_stmt = select(func.count(PlatformTemplate.id)).where(
            PlatformTemplate.is_active.is_(True)
        )
        stmt = (
            select(PlatformTemplate)
            .where(PlatformTemplate.is_active.is_(True))
            .order_by(PlatformTemplate.category.nulls_last(), PlatformTemplate.title)
        )

    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

    result = await session.execute(stmt)
    templates = list(result.scalars().all())

    logger.debug(
        "list_platform_templates: category=%s page=%d limit=%d "
        "returned %d of %d total results",
        category,
        page,
        limit,
        len(templates),
        total,
    )
    return templates, total


async def get_platform_template(
    session: AsyncSession,
    template_id: UUID,
) -> PlatformTemplate:
    result = await session.execute(
        select(PlatformTemplate).where(
            PlatformTemplate.id == template_id,
            PlatformTemplate.is_active.is_(True),
        )
    )
    template = result.scalars().first()
    if template is None:
        raise PlatformTemplateNotFoundError

    return template


async def duplicate_template(
    session: AsyncSession,
    organiser_id: UUID,
    template_id: UUID,
) -> OrganiserTemplate:
    result = await session.execute(
        select(OrganiserTemplate)
        .options(selectinload(OrganiserTemplate.hashtags))
        .where(
            OrganiserTemplate.id == template_id,
            OrganiserTemplate.deleted_at.is_(None),
        )
    )
    original = result.scalars().first()
    if original is None:
        raise OrganiserTemplateNotFoundError

    if original.organiser_id != organiser_id:
        raise NotTemplateOwnerError

    copy = OrganiserTemplate(
        organiser_id=organiser_id,
        platform_template_id=original.platform_template_id,
        title=f"{original.title} (Copy)",
        canvas_data=original.canvas_data,
        default_caption=original.default_caption,
        destination_link=original.destination_link,
        thumbnail_url=original.thumbnail_url,
        logo_url=None,
        logo_public_id=None,
        access_type=original.access_type,
        is_published=False,
        share_slug=None,
        published_at=None,
    )
    session.add(copy)
    await session.flush()

    for tag in original.hashtags:
        session.add(TemplateHashtag(template_id=copy.id, hashtag=tag.hashtag))

    await session.commit()
    await session.refresh(copy)

    logger.info(
        "Duplicated template %s as %s for organiser %s",
        template_id,
        copy.id,
        organiser_id,
    )
    return copy


async def list_organiser_templates(
    session: AsyncSession,
    organiser_id: UUID,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[OrganiserTemplate], int]:
    base_conditions = (
        OrganiserTemplate.organiser_id == organiser_id,
        OrganiserTemplate.deleted_at.is_(None),
    )

    count_result = await session.execute(
        select(func.count(OrganiserTemplate.id)).where(*base_conditions)
    )
    total = count_result.scalar_one()

    stmt = (
        select(OrganiserTemplate)
        .where(*base_conditions)
        .order_by(
            OrganiserTemplate.updated_at.desc().nulls_last(),
            OrganiserTemplate.created_at.desc().nulls_last(),
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    templates = list(result.scalars().all())

    logger.debug(
        "list_organiser_templates: organiser=%s page=%d limit=%d "
        "returned %d of %d total",
        organiser_id,
        page,
        limit,
        len(templates),
        total,
    )
    return templates, total


async def delete_organiser_template(
    session: AsyncSession,
    organiser_id: UUID,
    template_id: UUID,
) -> None:
    result = await session.execute(
        select(OrganiserTemplate)
        .options(selectinload(OrganiserTemplate.badges))
        .where(
            OrganiserTemplate.id == template_id,
            OrganiserTemplate.deleted_at.is_(None),
        )
    )
    template = result.scalars().first()
    if template is None:
        raise OrganiserTemplateNotFoundError
    if template.organiser_id != organiser_id:
        raise NotTemplateOwnerError

    logo_public_id = template.logo_public_id
    badge_public_ids = [
        badge.badge_public_id for badge in template.badges if badge.badge_public_id
    ]

    await session.delete(template)
    await session.commit()

    logger.info(
        "Deleted organiser template %s (organiser=%s)",
        template_id,
        organiser_id,
    )

    if logo_public_id:
        try:
            await delete_logo(logo_public_id)
        except CloudinaryUploadError:
            logger.warning(
                "Failed to delete logo asset %s for template %s from Cloudinary "
                "— manual cleanup may be required",
                logo_public_id,
                template_id,
            )
        except Exception:
            logger.warning(
                "Failed to delete logo asset %s for template %s from Cloudinary "
                "— manual cleanup may be required",
                logo_public_id,
                template_id,
            )

    for public_id in badge_public_ids:
        try:
            await delete_asset(public_id)
        except CloudinaryUploadError:
            logger.warning(
                "Failed to delete badge image asset %s for template %s from Cloudinary"
                " — manual cleanup may be required",
                public_id,
                template_id,
            )
        except Exception:
            logger.warning(
                "Failed to delete badge image asset %s for template %s from Cloudinary"
                " — manual cleanup may be required",
                public_id,
                template_id,
            )


async def edit_organiser_template(
    session: AsyncSession,
    organiser_id: UUID,
    template_id: UUID,
    field_updates: dict[str, Any],
    new_hashtags: list[str] | None,
    update_hashtags: bool,
) -> OrganiserTemplate:
    result = await session.execute(
        select(OrganiserTemplate)
        .options(selectinload(OrganiserTemplate.hashtags))
        .where(
            OrganiserTemplate.id == template_id,
            OrganiserTemplate.deleted_at.is_(None),
        )
    )
    template = result.scalars().first()
    if template is None:
        raise OrganiserTemplateNotFoundError
    if template.organiser_id != organiser_id:
        raise NotTemplateOwnerError

    for field, value in field_updates.items():
        setattr(template, field, value)

    if update_hashtags:
        template.hashtags.clear()
        for tag in new_hashtags or []:
            template.hashtags.append(TemplateHashtag(hashtag=tag))

    await session.commit()

    # Re-query after commit to return a fully consistent object with
    # the updated hashtag relationship loaded.
    refreshed = await session.execute(
        select(OrganiserTemplate)
        .options(selectinload(OrganiserTemplate.hashtags))
        .where(OrganiserTemplate.id == template_id)
    )
    return refreshed.scalars().one()
