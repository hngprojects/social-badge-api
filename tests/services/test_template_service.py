import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotTemplateOwnerError, OrganiserTemplateNotFoundError
from app.models import OrganiserTemplate, PlatformTemplate, User
from app.models.templates import TemplateHashtag
from app.services.template import duplicate_template


@pytest.fixture
async def platform_template(db_session: AsyncSession) -> PlatformTemplate:
    template = PlatformTemplate(
        title="Base Layout",
        category="conferences",
        canvas_data={"layout_id": "name_role_dark_v1"},
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def organiser(db_session: AsyncSession) -> User:
    from app.core.security import hash_password

    user = User(
        first_name="Organiser",
        last_name="One",
        email="organiser-dup@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def source_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> OrganiserTemplate:
    template = OrganiserTemplate(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Original Event",
        canvas_data={"layout_id": "name_role_dark_v1", "accent": "#FF5733"},
        default_caption="Join us at Original Event!",
        destination_link="https://event.example.com",
        thumbnail_url="https://cdn.example.com/thumb.png",
        logo_url="https://cdn.example.com/logo.png",
        logo_public_id="template-logos/logo-abc",
        access_type=0,
    )
    db_session.add(template)
    await db_session.flush()

    for tag in ["#OriginalEvent", "#2026"]:
        db_session.add(TemplateHashtag(template_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def published_source_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> OrganiserTemplate:
    from datetime import UTC, datetime

    template = OrganiserTemplate(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Published Event",
        canvas_data={"layout_id": "photo_gradient_v1"},
        is_published=True,
        share_slug="pub-slug-001",
        published_at=datetime.now(UTC),
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def test_duplicate_returns_new_record(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    assert copy.id != source_template.id
    assert copy.id is not None


async def test_duplicate_copy_title_has_suffix(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    assert copy.title == "Original Event (Copy)"


async def test_duplicate_copies_canvas_data(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    assert copy.canvas_data == source_template.canvas_data


async def test_duplicate_copies_all_config_fields(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    assert copy.default_caption == source_template.default_caption
    assert copy.destination_link == source_template.destination_link
    assert copy.thumbnail_url == source_template.thumbnail_url
    assert copy.logo_url == source_template.logo_url
    assert copy.logo_public_id == source_template.logo_public_id
    assert copy.access_type == source_template.access_type
    assert copy.platform_template_id == source_template.platform_template_id
    assert copy.organiser_id == source_template.organiser_id


async def test_duplicate_copy_is_draft(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    assert copy.is_published is False
    assert copy.share_slug is None
    assert copy.published_at is None


async def test_duplicate_published_template_copy_is_still_draft(
    db_session: AsyncSession,
    organiser: User,
    published_source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=published_source_template.id,
    )

    assert copy.is_published is False
    assert copy.share_slug is None
    assert copy.published_at is None


async def test_duplicate_copies_hashtags(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    result = await db_session.execute(
        select(TemplateHashtag).where(TemplateHashtag.template_id == copy.id)
    )
    copy_tags = sorted(tag.hashtag for tag in result.scalars().all())

    assert copy_tags == ["#2026", "#OriginalEvent"]


async def test_duplicate_original_unchanged(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    original_title = source_template.title
    original_canvas = source_template.canvas_data
    original_slug = source_template.share_slug

    await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    await db_session.refresh(source_template)
    assert source_template.title == original_title
    assert source_template.canvas_data == original_canvas
    assert source_template.share_slug == original_slug


async def test_duplicate_persists_to_database(
    db_session: AsyncSession,
    organiser: User,
    source_template: OrganiserTemplate,
) -> None:
    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=source_template.id,
    )

    fetched = await db_session.get(OrganiserTemplate, copy.id)
    assert fetched is not None
    assert fetched.title == "Original Event (Copy)"


async def test_duplicate_template_without_hashtags(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    bare = OrganiserTemplate(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="No Tags Event",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(bare)
    await db_session.commit()
    await db_session.refresh(bare)

    copy = await duplicate_template(
        session=db_session,
        organiser_id=organiser.id,
        template_id=bare.id,
    )

    result = await db_session.execute(
        select(TemplateHashtag).where(TemplateHashtag.template_id == copy.id)
    )
    assert result.scalars().all() == []


async def test_duplicate_raises_not_found_for_missing_template(
    db_session: AsyncSession,
    organiser: User,
) -> None:
    with pytest.raises(OrganiserTemplateNotFoundError):
        await duplicate_template(
            session=db_session,
            organiser_id=organiser.id,
            template_id=uuid.uuid4(),
        )


async def test_duplicate_raises_not_found_for_soft_deleted_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    deleted = OrganiserTemplate(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Deleted Event",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(deleted)
    await db_session.commit()
    await db_session.refresh(deleted)

    with pytest.raises(OrganiserTemplateNotFoundError):
        await duplicate_template(
            session=db_session,
            organiser_id=organiser.id,
            template_id=deleted.id,
        )


async def test_duplicate_raises_not_owner_for_other_user(
    db_session: AsyncSession,
    source_template: OrganiserTemplate,
) -> None:
    with pytest.raises(NotTemplateOwnerError):
        await duplicate_template(
            session=db_session,
            organiser_id=uuid.uuid4(),
            template_id=source_template.id,
        )
