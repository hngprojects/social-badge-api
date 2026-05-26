import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlatformTemplate
from app.services.admin import (
    create_platform_template,
    delete_platform_template,
    get_platform_template,
    update_platform_template,
)


async def test_create_platform_template_persists(
    db_session: AsyncSession,
) -> None:
    template = await create_platform_template(
        session=db_session,
        title="Service Template",
        category="Service",
        canvas_data={"layout": "v1"},
        thumbnail_url="https://example.com/thumb.png",
        is_active=True,
    )

    result = await db_session.execute(
        select(PlatformTemplate).where(PlatformTemplate.id == template.id)
    )
    stored = result.scalars().first()
    assert stored is not None
    assert stored.title == "Service Template"
    assert stored.category == "Service"
    assert stored.canvas_data == {"layout": "v1"}
    assert stored.thumbnail_url == "https://example.com/thumb.png"
    assert stored.is_active is True


async def test_get_platform_template_returns_none_when_missing(
    db_session: AsyncSession,
) -> None:
    result = await get_platform_template(
        session=db_session,
        template_id=uuid.uuid4(),
    )
    assert result is None


async def test_get_platform_template_returns_record(
    db_session: AsyncSession,
) -> None:
    template = PlatformTemplate(
        title="Lookup",
        category="LookupCat",
        canvas_data={"layout": "lookup"},
        thumbnail_url=None,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    result = await get_platform_template(
        session=db_session,
        template_id=template.id,
    )
    assert result is not None
    assert result.id == template.id
    assert result.title == "Lookup"


async def test_update_platform_template_updates_fields(
    db_session: AsyncSession,
) -> None:
    template = PlatformTemplate(
        title="Old Title",
        category="Old Category",
        canvas_data={"layout": "old"},
        thumbnail_url="https://example.com/old.png",
        is_active=True,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    updated = await update_platform_template(
        session=db_session,
        template=template,
        title="New Title",
        category="New Category",
        canvas_data={"layout": "new"},
        thumbnail_url="https://example.com/new.png",
        is_active=False,
    )

    assert updated.title == "New Title"
    assert updated.category == "New Category"
    assert updated.canvas_data == {"layout": "new"}
    assert updated.thumbnail_url == "https://example.com/new.png"
    assert updated.is_active is False


async def test_update_platform_template_keeps_unset_fields(
    db_session: AsyncSession,
) -> None:
    template = PlatformTemplate(
        title="Keep Title",
        category="Keep Category",
        canvas_data={"layout": "keep"},
        thumbnail_url="https://example.com/keep.png",
        is_active=True,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    updated = await update_platform_template(
        session=db_session,
        template=template,
        title=None,
        category=None,
        canvas_data=None,
        thumbnail_url=None,
        is_active=None,
    )

    assert updated.title == "Keep Title"
    assert updated.canvas_data == {"layout": "keep"}
    assert updated.thumbnail_url == "https://example.com/keep.png"
    assert updated.is_active is True


async def test_delete_platform_template_removes_record(
    db_session: AsyncSession,
) -> None:
    template = PlatformTemplate(
        title="Delete",
        category="Delete",
        canvas_data=None,
        thumbnail_url=None,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    await delete_platform_template(session=db_session, template=template)

    result = await db_session.get(PlatformTemplate, template.id)
    assert result is None
