"""Service layer for platform template CRUD operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.templates import PlatformTemplate


async def create_platform_template(
    session: AsyncSession,
    title: str,
    category: str,
    canvas_data: dict[Any, Any] | None,
    thumbnail_url: str | None,
    is_active: bool,
) -> PlatformTemplate:
    """Create and persist a new platform template."""
    template = PlatformTemplate(
        title=title,
        category=category,
        canvas_data=canvas_data,
        thumbnail_url=thumbnail_url,
        is_active=is_active,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def list_platform_templates(
    session: AsyncSession,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PlatformTemplate]:
    """Return platform templates, optionally filtered by category
    with limit/offset pagination."""
    stmt = select(PlatformTemplate)
    if category is not None:
        stmt = stmt.where(PlatformTemplate.category == category)
    stmt = stmt.order_by(PlatformTemplate.created_at.asc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_platform_template(
    session: AsyncSession, template_id: UUID
) -> PlatformTemplate | None:
    """Fetch a platform template by ID."""
    return await session.get(PlatformTemplate, template_id)


async def update_platform_template(
    session: AsyncSession,
    template: PlatformTemplate,
    title: str | None,
    category: str | None,
    canvas_data: dict[Any, Any] | None,
    thumbnail_url: str | None,
    is_active: bool | None,
) -> PlatformTemplate:
    """Update fields on a platform template and persist changes."""
    if title is not None:
        template.title = title
    if category is not None:
        template.category = category
    if canvas_data is not None:
        template.canvas_data = canvas_data
    if thumbnail_url is not None:
        template.thumbnail_url = thumbnail_url
    if is_active is not None:
        template.is_active = is_active
    await session.commit()
    await session.refresh(template)
    return template


async def delete_platform_template(
    session: AsyncSession, template: PlatformTemplate
) -> None:
    """Delete a platform template."""
    await session.delete(template)
    await session.commit()
