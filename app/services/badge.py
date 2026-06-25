import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy import update as sa_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    BadgeAlreadyPublishedError,
    BadgeNotFoundError,
    CloudinaryUploadError,
    NotBadgeOwnerError,
    PlatformTemplateNotActiveError,
    PlatformTemplateNotFoundError,
    PublicBadgeNotFoundError,
)
from app.core.slug import generate_share_slug
from app.models import Badge, BadgeHashtag, PlatformTemplate
from app.models.notifications import NotificationType
from app.services.cloudinary import (
    delete_logo,
    upload_logo,
)
from app.services.notification import create_notification

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset(
    {
        "festivals",
        "hackathons",
        "conferences",
        "community",
        "bootcamp",
        "meetups",
        "speakers",
        "summit",
        "trending",
    }
)


async def _increment_template_badge_count(
    session: AsyncSession, platform_template_id: UUID
) -> None:
    """Increments the total count of badges generated using a specific platform
    template.

    Performs an in-place atomic update query in the database.
    """
    await session.execute(
        sa_update(PlatformTemplate)
        .where(PlatformTemplate.id == platform_template_id)
        .values(total_badges_made=PlatformTemplate.total_badges_made + 1)
    )


async def create_badge(
    session: AsyncSession,
    organiser_id: UUID,
    platform_template_id: UUID,
) -> Badge:
    """Creates and persists a new badge instance based on a platform template.

    Verifies that the platform template exists and is active.
    Clones properties such as title and canvas data from the platform template,
    increments the template's badge count, commits the database transaction,
    and returns the created badge.

    Raises:
        PlatformTemplateNotFoundError: If the platform template does not exist.
        PlatformTemplateNotActiveError: If the platform template is inactive.
    """
    result = await session.execute(
        select(PlatformTemplate).where(
            PlatformTemplate.id == platform_template_id,
        )
    )
    platform_template = result.scalars().first()
    if platform_template is None:
        raise PlatformTemplateNotFoundError

    if not platform_template.is_active:
        raise PlatformTemplateNotActiveError

    instance = Badge(
        organiser_id=organiser_id,
        platform_template_id=platform_template_id,
        title=platform_template.title,
        canvas_data=platform_template.canvas_data or {},
    )
    session.add(instance)
    await session.flush()
    await _increment_template_badge_count(session, platform_template_id)

    await session.commit()
    await session.refresh(instance)

    logger.info(
        "Created template instance %s for organiser %s",
        instance.id,
        organiser_id,
    )
    return instance


async def publish_badge(
    session: AsyncSession,
    organiser_id: UUID,
    id: UUID,
) -> Badge:
    """Publishes a badge to make it publicly viewable.

    Marks the badge as published, sets its publication timestamp,
    and assigns a unique share slug if one hasn't been generated yet.
    Commits the transaction and refreshes the badge.

    Raises:
        BadgeNotFoundError: If the badge is not found.
        NotBadgeOwnerError: If the badge does not belong to the requesting organiser.
        BadgeAlreadyPublishedError: If the badge has already been published.
    """
    result = await session.execute(
        select(Badge).where(
            Badge.id == id,
            Badge.deleted_at.is_(None),
        )
    )
    badge = result.scalars().first()

    if not badge:
        raise BadgeNotFoundError
    if badge.organiser_id != organiser_id:
        raise NotBadgeOwnerError
    if badge.is_published:
        raise BadgeAlreadyPublishedError

    badge.is_published = True
    badge.published_at = datetime.now(UTC)

    if not badge.share_slug:
        badge.share_slug = generate_share_slug()

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise

    await session.refresh(badge)

    logger.info(
        "Published badge %s by organiser %s",
        badge.id,
        organiser_id,
    )

    return badge


async def unpublish_badge(
    session: AsyncSession,
    organiser_id: UUID,
    id: UUID,
) -> Badge:
    """Unpublishes an active badge, removing its public visibility.

    Resets the publication status and timestamp of the badge,
    commits the changes to the database, and refreshes the object.

    Raises:
        BadgeNotFoundError: If the badge is not found or has been soft-deleted.
        NotBadgeOwnerError: If the badge does not belong to the requesting organiser.
    """
    result = await session.execute(select(Badge).where(Badge.id == id))
    template = result.scalars().first()
    if template is None or template.deleted_at is not None:
        raise BadgeNotFoundError
    if template.organiser_id != organiser_id:
        raise NotBadgeOwnerError

    template.is_published = False
    template.published_at = None
    await session.commit()
    await session.refresh(template)

    logger.info("Unpublished template %s by organiser %s", template.id, organiser_id)
    return template


async def upload_badge_logo(
    session: AsyncSession,
    id: UUID,
    organiser_id: UUID,
    image_data: bytes,
) -> str:
    """Uploads a logo for a badge to Cloudinary and persists the URL in the database.

    Retrieves the badge, uploads the logo binary to Cloudinary,
    updates logo metadata (URL and public ID), and commits.
    If the DB commit fails, rolls back the transaction
    and attempts to delete the newly uploaded asset from Cloudinary.
    Deletes any pre-existing badge logo from Cloudinary on successful commit.

    Raises:
        BadgeNotFoundError: If the badge is not found.
        NotBadgeOwnerError: If the badge does not belong to the requesting organiser.
    """
    result = await session.execute(
        select(Badge).where(
            Badge.id == id,
            Badge.deleted_at.is_(None),
        )
    )
    instance = result.scalars().first()

    if instance is None:
        raise BadgeNotFoundError

    if instance.organiser_id != organiser_id:
        raise NotBadgeOwnerError

    old_public_id = instance.logo_public_id

    logo_url, public_id = await upload_logo(image_data)

    instance.logo_url = logo_url
    instance.logo_public_id = public_id
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        try:
            await delete_logo(public_id)
        except Exception:
            logger.warning(
                "Failed to clean up Cloudinary asset %s after DB commit failure",
                public_id,
            )
        raise
    await session.refresh(instance)

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
        id,
        public_id,
    )
    return logo_url


async def get_public_badge_by_slug(
    session: AsyncSession,
    slug: str,
) -> Badge:
    """Fetches a published badge along with its hashtags using its share slug.

    Performs a public lookup of non-deleted, published badges.

    Raises:
        PublicBadgeNotFoundError: If the badge cannot be resolved.
    """
    result = await session.execute(
        select(Badge)
        .options(selectinload(Badge.hashtags))
        .where(
            Badge.share_slug == slug,
            Badge.is_published.is_(True),
            Badge.deleted_at.is_(None),
        )
    )
    template = result.scalars().first()
    if template is None:
        raise PublicBadgeNotFoundError

    logger.info("Public lookup for slug %s resolved to template %s", slug, template.id)
    return template


_PUBLIC_WHERE = (
    Badge.is_published.is_(True),
    Badge.deleted_at.is_(None),
)


async def increment_badge_share_count(session: AsyncSession, slug: str) -> None:
    """Atomically increments the share count of a published badge by one.

    Performs an update query on the database using the badge's share slug.

    Raises:
        PublicBadgeNotFoundError: If the badge is not found, not published,
        or soft-deleted.
    """
    result = cast(
        CursorResult[Any],
        await session.execute(
            sa_update(Badge)
            .where(Badge.share_slug == slug, *_PUBLIC_WHERE)
            .values(share_count=Badge.share_count + 1)
        ),
    )
    await session.commit()
    if result.rowcount == 0:
        raise PublicBadgeNotFoundError


async def increment_badge_creation_count(session: AsyncSession, slug: str) -> None:
    """Atomically increments the creation count of a published badge and creates a
    notification.

    Increments the creation_count in the database,
    retrieves the badge's metadata,
    and generates a BADGE_CREATION notification for the badge's organiser.
    Commits the transaction.

    Raises:
        PublicBadgeNotFoundError: If the badge is not found, not published,
        or soft-deleted.
    """
    result = await session.execute(
        sa_update(Badge)
        .where(Badge.share_slug == slug, *_PUBLIC_WHERE)
        .values(creation_count=Badge.creation_count + 1)
        .returning(Badge.id, Badge.organiser_id, Badge.title)
    )
    row = result.first()

    if row is None:
        raise PublicBadgeNotFoundError

    badge_id, organiser_id, badge_title = row

    await create_notification(
        session=session,
        user_id=organiser_id,
        notif_type=NotificationType.BADGE_CREATION,
        title="A new participant has just created a new badge",
        body=f"A new participant just created a badge from '{badge_title}'.",
        extra_data={"badge_id": str(badge_id), "share_slug": slug},
    )

    await session.commit()


async def list_platform_templates(
    session: AsyncSession,
    category: str | None = None,
    page: int = 1,
    limit: int = 10,
) -> tuple[list[PlatformTemplate], int]:
    """Retrieves a paginated list of active platform templates, optionally filtered by
    category.

    Validates the category if provided, counts the total matching templates,
    and returns a tuple containing the matching templates list and the total count.

    Raises:
        ValueError: If the category is not recognized.
    """
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
        "list_platform_templates: category=%s page=%d limit=%d returned %d of %d total results",  # noqa: E501
        category,
        page,
        limit,
        len(templates),
        total,
    )
    return templates, total


async def get_platform_template(
    session: AsyncSession,
    id: UUID,
) -> PlatformTemplate:
    """Fetches a single active platform template by its identifier.

    Raises:
        PlatformTemplateNotFoundError: If the template is not found or is inactive.
    """
    result = await session.execute(
        select(PlatformTemplate).where(
            PlatformTemplate.id == id,
            PlatformTemplate.is_active.is_(True),
        )
    )
    template = result.scalars().first()
    if template is None:
        raise PlatformTemplateNotFoundError

    return template


async def duplicate_badge(
    session: AsyncSession,
    organiser_id: UUID,
    id: UUID,
) -> Badge:
    """Duplicates an existing badge and its hashtags for the same organiser.

    Fetches the original badge, creates a new Badge record containing the cloned fields
    with copy suffixes and cleared publication/slug/logo fields,
    duplicates associated hashtags, increments the template usage count,
    and commits the transaction.

    Raises:
        BadgeNotFoundError: If the original badge is not found or has been soft-deleted.
        NotBadgeOwnerError: If the original badge does not belong
        to the requesting organiser.
    """
    result = await session.execute(
        select(Badge)
        .options(selectinload(Badge.hashtags))
        .where(
            Badge.id == id,
            Badge.deleted_at.is_(None),
        )
    )
    original = result.scalars().first()
    if original is None:
        raise BadgeNotFoundError

    if original.organiser_id != organiser_id:
        raise NotBadgeOwnerError

    copy = Badge(
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
        access_code=original.access_code,
        is_published=False,
        share_slug=None,
        published_at=None,
    )
    session.add(copy)
    await session.flush()

    for tag in original.hashtags:
        session.add(BadgeHashtag(badge_id=copy.id, hashtag=tag.hashtag))

    await _increment_template_badge_count(session, original.platform_template_id)

    await session.commit()
    await session.refresh(copy)

    logger.info(
        "Duplicated template %s as %s for organiser %s",
        id,
        copy.id,
        organiser_id,
    )
    return copy


async def list_badges(
    session: AsyncSession,
    organiser_id: UUID,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Badge], int]:
    """Retrieves a paginated list of non-deleted badges owned by a specific organiser.

    Orders the badges by last updated and creation times, and returns a tuple containing
    the list of badges and the total number of badges matching the query.
    """
    base_conditions = (
        Badge.organiser_id == organiser_id,
        Badge.deleted_at.is_(None),
    )

    count_result = await session.execute(
        select(func.count(Badge.id)).where(*base_conditions)
    )
    total = count_result.scalar_one()

    stmt = (
        select(Badge)
        .where(*base_conditions)
        .order_by(
            Badge.updated_at.desc().nulls_last(),
            Badge.created_at.desc().nulls_last(),
        )
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    templates = list(result.scalars().all())

    logger.debug(
        "list_badges: organiser=%s page=%d limit=%d returned %d of %d total",
        organiser_id,
        page,
        limit,
        len(templates),
        total,
    )
    return templates, total


async def delete_badge(
    session: AsyncSession,
    organiser_id: UUID,
    id: UUID,
) -> None:
    """Soft-deletes a badge and deletes its logo from Cloudinary.

    Sets the deleted_at timestamp on the badge record, unpublishes it, and commits.
    Once the transaction is committed, attempts to delete the logo from Cloudinary.

    Raises:
        BadgeNotFoundError: If the badge is not found or has already been soft-deleted.
        NotBadgeOwnerError: If the badge does not belong to the requesting organiser.
    """
    result = await session.execute(
        select(Badge).where(
            Badge.id == id,
            Badge.deleted_at.is_(None),
        )
    )
    template = result.scalars().first()
    if template is None:
        raise BadgeNotFoundError
    if template.organiser_id != organiser_id:
        raise NotBadgeOwnerError

    logo_public_id = template.logo_public_id

    template.deleted_at = datetime.now(UTC)
    template.is_published = False
    template.published_at = None
    await session.commit()

    logger.info(
        "Deleted organiser template %s (organiser=%s)",
        id,
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
                id,
            )
        except Exception:
            logger.warning(
                "Failed to delete logo asset %s for template %s from Cloudinary "
                "— manual cleanup may be required",
                logo_public_id,
                id,
            )


async def get_badge_by_id(
    session: AsyncSession,
    organiser_id: UUID,
    id: UUID,
) -> Badge:
    """Retrieves a non-deleted badge and its hashtags by its unique identifier.

    Verifies ownership before returning the database record.

    Raises:
        BadgeNotFoundError: If the badge is not found or has been soft-deleted.
        NotBadgeOwnerError: If the badge does not belong to the requesting organiser.
    """
    result = await session.execute(
        select(Badge)
        .options(selectinload(Badge.hashtags))
        .where(
            Badge.id == id,
            Badge.deleted_at.is_(None),
        )
    )
    badge = result.scalars().first()
    if badge is None:
        raise BadgeNotFoundError
    if badge.organiser_id != organiser_id:
        raise NotBadgeOwnerError

    return badge


async def edit_badge(
    session: AsyncSession,
    organiser_id: UUID,
    id: UUID,
    field_updates: dict[str, Any],
    new_hashtags: list[str] | None,
    update_hashtags: bool,
) -> Badge:
    """Modifies an existing badge's details, access controls, and hashtags.

    Applies attribute updates, validates private access codes
    (between 4 and 10 characters), replaces existing hashtags if specified,
    commits the transaction, and returns the refreshed badge.

    Raises:
        BadgeNotFoundError: If the badge is not found or is soft-deleted.
        NotBadgeOwnerError: If the badge does not belong to the requesting organiser.
        ValueError: If private access controls are invalid or access_type is invalid.
    """
    result = await session.execute(
        select(Badge)
        .options(selectinload(Badge.hashtags))
        .where(
            Badge.id == id,
            Badge.deleted_at.is_(None),
        )
    )
    badge = result.scalars().first()
    if badge is None:
        raise BadgeNotFoundError
    if badge.organiser_id != organiser_id:
        raise NotBadgeOwnerError

    if "access_type" in field_updates or "access_code" in field_updates:
        target_type = field_updates.get("access_type", badge.access_type)
        target_code = field_updates.get("access_code", badge.access_code)

        if target_type == 1:
            if not target_code or len(target_code) < 4 or len(target_code) > 10:
                raise ValueError(
                    "access_code is required and must be between 4 and 10 characters "
                    "when access_type is private."
                )
            field_updates["access_code"] = target_code
        elif target_type == 0:
            field_updates["access_code"] = None
        else:
            raise ValueError("access_type must be 0 (public) or 1 (private).")

    for field, value in field_updates.items():
        setattr(badge, field, value)

    if update_hashtags:
        badge.hashtags.clear()
        for tag in new_hashtags or []:
            badge.hashtags.append(BadgeHashtag(hashtag=tag))

    await session.commit()

    refreshed = await session.execute(
        select(Badge).options(selectinload(Badge.hashtags)).where(Badge.id == id)
    )
    return refreshed.scalars().one()


async def get_badge_analytics(
    session: AsyncSession,
    organiser_id: UUID,
) -> tuple[int, int, int, int, list[tuple[UUID, int]]]:
    """Calculates aggregates and platform template usage analytics for an organiser's
    badges.

    Queries the database to calculate total badges, active (published) badges, overall
    shares, overall creations, and templates usage counts sorted by frequency.
    """
    base_conditions = (
        Badge.organiser_id == organiser_id,
        Badge.deleted_at.is_(None),
    )

    scalar_stmt = select(
        func.count(Badge.id).label("total"),
        func.coalesce(
            func.sum(case((Badge.is_published.is_(True), 1), else_=0)), 0
        ).label("active"),
        func.coalesce(func.sum(Badge.share_count), 0).label("total_shares"),
        func.coalesce(func.sum(Badge.creation_count), 0).label("total_creations"),
    ).where(*base_conditions)

    scalar_result = await session.execute(scalar_stmt)
    total, active, total_shares, total_creations = scalar_result.one()

    usage_stmt = (
        select(
            Badge.platform_template_id,
            func.count(Badge.id).label("badge_count"),
        )
        .where(*base_conditions)
        .group_by(Badge.platform_template_id)
        .order_by(func.count(Badge.id).desc())
    )
    usage_rows = (await session.execute(usage_stmt)).all()

    return (
        int(total),
        int(active),
        int(total_shares),
        int(total_creations),
        [(row.platform_template_id, int(row.badge_count)) for row in usage_rows],
    )
