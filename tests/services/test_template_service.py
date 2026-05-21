import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotTemplateOwnerError, OrganiserTemplateNotFoundError
from app.core.security import hash_password
from app.models import OrganiserTemplate, PlatformTemplate, User
from app.models.templates import TemplateHashtag
from app.services.template import duplicate_template, list_organiser_templates


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
    assert copy.logo_url is None
    assert copy.logo_public_id is None
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


async def _make_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
    *,
    title: str = "Event",
    is_published: bool = False,
    deleted: bool = False,
    updated_at_offset_seconds: int = 0,
) -> OrganiserTemplate:
    now = datetime.now(UTC)
    template = OrganiserTemplate(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title=title,
        canvas_data={"layout_id": "v1"},
        is_published=is_published,
        share_slug=f"slug-{title.lower().replace(' ', '-')}" if is_published else None,
        deleted_at=now if deleted else None,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    if updated_at_offset_seconds:
        from sqlalchemy import update as sa_update

        await db_session.execute(
            sa_update(OrganiserTemplate)
            .where(OrganiserTemplate.id == template.id)
            .values(updated_at=now + timedelta(seconds=updated_at_offset_seconds))
        )
        await db_session.commit()
        await db_session.refresh(template)

    return template


async def test_returns_empty_list_when_no_templates(
    db_session: AsyncSession,
    organiser: User,
) -> None:
    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
    )

    assert templates == []
    assert total == 0


async def test_returns_all_templates_for_organiser(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    for i in range(3):
        await _make_template(
            db_session, organiser, platform_template, title=f"Event {i}"
        )

    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
    )

    assert total == 3
    assert len(templates) == 3


async def test_excludes_soft_deleted_templates(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    await _make_template(db_session, organiser, platform_template, title="Live Event")
    await _make_template(
        db_session, organiser, platform_template, title="Deleted Event", deleted=True
    )

    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
    )

    assert total == 1
    assert templates[0].title == "Live Event"


async def test_excludes_other_organisers_templates(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    other = User(
        first_name="Other",
        last_name="Organiser",
        email="other-list@example.com",
        password_hash=hash_password("StrongPassword1!"),
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    await _make_template(db_session, organiser, platform_template, title="My Event")
    await _make_template(db_session, other, platform_template, title="Their Event")

    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
    )

    assert total == 1
    assert templates[0].title == "My Event"


async def test_returns_zero_for_unknown_organiser(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    await _make_template(db_session, organiser, platform_template, title="Some Event")

    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=uuid.uuid4(),
    )

    assert total == 0
    assert templates == []


async def test_orders_by_most_recently_updated_first(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    await _make_template(
        db_session,
        organiser,
        platform_template,
        title="Older",
        updated_at_offset_seconds=0,
    )
    await _make_template(
        db_session,
        organiser,
        platform_template,
        title="Newer",
        updated_at_offset_seconds=60,
    )

    templates, _ = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
    )

    assert templates[0].title == "Newer"
    assert templates[1].title == "Older"


async def test_includes_both_published_and_draft_templates(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    await _make_template(
        db_session,
        organiser,
        platform_template,
        title="Draft Event",
        is_published=False,
    )
    await _make_template(
        db_session,
        organiser,
        platform_template,
        title="Published Event",
        is_published=True,
    )

    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
    )

    assert total == 2
    statuses = {t.title: t.is_published for t in templates}
    assert statuses["Draft Event"] is False
    assert statuses["Published Event"] is True


async def test_pagination_total_reflects_full_count(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    for i in range(5):
        await _make_template(
            db_session, organiser, platform_template, title=f"Event {i}"
        )

    _, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
        page=1,
        limit=2,
    )

    assert total == 5


async def test_pagination_page_two_returns_correct_slice(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    for i in range(5):
        await _make_template(
            db_session,
            organiser,
            platform_template,
            title=f"Event {i}",
            updated_at_offset_seconds=i * 10,
        )

    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
        page=2,
        limit=2,
    )

    assert total == 5
    assert len(templates) == 2


async def test_pagination_beyond_last_page_returns_empty(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    await _make_template(db_session, organiser, platform_template, title="Only Event")

    templates, total = await list_organiser_templates(
        session=db_session,
        organiser_id=organiser.id,
        page=99,
        limit=20,
    )

    assert total == 1
    assert templates == []
