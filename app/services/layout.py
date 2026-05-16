from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.templates import PlatformTemplate
from app.schemas.layout import LayoutResponse, PaginatedLayouts


async def list_layouts(
    session: AsyncSession,
    page: int = 1,
    limit: int = 10,
) -> PaginatedLayouts:
    """
    Fetch paginated active layout templates.
    """
    offset = (page - 1) * limit

    total = await session.scalar(
        select(func.count())
        .select_from(PlatformTemplate)
        .where(PlatformTemplate.is_active.is_(True))
    )

    result = await session.execute(
        select(PlatformTemplate)
        .where(PlatformTemplate.is_active.is_(True))
        .order_by(
            PlatformTemplate.title,
            PlatformTemplate.created_at,
        )
        .offset(offset)
        .limit(limit)
    )

    templates = result.scalars().all()

    layouts = [
        LayoutResponse.model_validate(
            {
                "layout_id": template.id,
                "name": template.title,
                "description": template.description,
                "thumbnail_url": template.thumbnail_url,
            }
        )
        for template in templates
    ]

    return PaginatedLayouts(
        page=page,
        limit=limit,
        total=total or 0,
        layouts=layouts,
    )
    