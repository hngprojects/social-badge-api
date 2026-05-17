import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import (
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
from app.services.cloudinary import delete_logo, upload_logo

logger = logging.getLogger(__name__)


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
