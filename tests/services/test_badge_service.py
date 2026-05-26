import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadgeNotFoundError, NotBadgeOwnerError
from app.core.security import hash_password
from app.models import Badge, BadgeHashtag, PlatformTemplate, User
from app.services.badge import (
    delete_badge,
    duplicate_badge,
    edit_badge,
    list_badges,
)


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
) -> Badge:
    template = Badge(
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
        db_session.add(BadgeHashtag(badge_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def published_source_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> Badge:
    from datetime import UTC, datetime

    template = Badge(
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
    source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
    )

    assert copy.id != source_template.id
    assert copy.id is not None


async def test_duplicate_copy_title_has_suffix(
    db_session: AsyncSession,
    organiser: User,
    source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
    )

    assert copy.title == "Original Event (Copy)"


async def test_duplicate_copies_canvas_data(
    db_session: AsyncSession,
    organiser: User,
    source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
    )

    assert copy.canvas_data == source_template.canvas_data


async def test_duplicate_copies_all_config_fields(
    db_session: AsyncSession,
    organiser: User,
    source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
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
    source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
    )

    assert copy.is_published is False
    assert copy.share_slug is None
    assert copy.published_at is None


async def test_duplicate_published_template_copy_is_still_draft(
    db_session: AsyncSession,
    organiser: User,
    published_source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=published_source_template.id,
    )

    assert copy.is_published is False
    assert copy.share_slug is None
    assert copy.published_at is None


async def test_duplicate_copies_hashtags(
    db_session: AsyncSession,
    organiser: User,
    source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
    )

    result = await db_session.execute(
        select(BadgeHashtag).where(BadgeHashtag.badge_id == copy.id)
    )
    copy_tags = sorted(tag.hashtag for tag in result.scalars().all())

    assert copy_tags == ["#2026", "#OriginalEvent"]


async def test_duplicate_original_unchanged(
    db_session: AsyncSession,
    organiser: User,
    source_template: Badge,
) -> None:
    original_title = source_template.title
    original_canvas = source_template.canvas_data
    original_slug = source_template.share_slug

    await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
    )

    await db_session.refresh(source_template)
    assert source_template.title == original_title
    assert source_template.canvas_data == original_canvas
    assert source_template.share_slug == original_slug


async def test_duplicate_persists_to_database(
    db_session: AsyncSession,
    organiser: User,
    source_template: Badge,
) -> None:
    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=source_template.id,
    )

    fetched = await db_session.get(Badge, copy.id)
    assert fetched is not None
    assert fetched.title == "Original Event (Copy)"


async def test_duplicate_template_without_hashtags(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    bare = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="No Tags Event",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(bare)
    await db_session.commit()
    await db_session.refresh(bare)

    copy = await duplicate_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=bare.id,
    )

    result = await db_session.execute(
        select(BadgeHashtag).where(BadgeHashtag.badge_id == copy.id)
    )
    assert result.scalars().all() == []


async def test_duplicate_raises_not_found_for_missing_template(
    db_session: AsyncSession,
    organiser: User,
) -> None:
    with pytest.raises(BadgeNotFoundError):
        await duplicate_badge(
            session=db_session,
            organiser_id=organiser.id,
            id=uuid.uuid4(),
        )


async def test_duplicate_raises_not_found_for_soft_deleted_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    deleted = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Deleted Event",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(deleted)
    await db_session.commit()
    await db_session.refresh(deleted)

    with pytest.raises(BadgeNotFoundError):
        await duplicate_badge(
            session=db_session,
            organiser_id=organiser.id,
            id=deleted.id,
        )


async def test_duplicate_raises_not_owner_for_other_user(
    db_session: AsyncSession,
    source_template: Badge,
) -> None:
    with pytest.raises(NotBadgeOwnerError):
        await duplicate_badge(
            session=db_session,
            organiser_id=uuid.uuid4(),
            id=source_template.id,
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
) -> Badge:
    now = datetime.now(UTC)
    template = Badge(
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
            sa_update(Badge)
            .where(Badge.id == template.id)
            .values(updated_at=now + timedelta(seconds=updated_at_offset_seconds))
        )
        await db_session.commit()
        await db_session.refresh(template)

    return template


async def test_returns_empty_list_when_no_templates(
    db_session: AsyncSession,
    organiser: User,
) -> None:
    templates, total = await list_badges(
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

    templates, total = await list_badges(
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

    templates, total = await list_badges(
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

    templates, total = await list_badges(
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

    templates, total = await list_badges(
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

    templates, _ = await list_badges(
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

    templates, total = await list_badges(
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

    _, total = await list_badges(
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

    templates, total = await list_badges(
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

    templates, total = await list_badges(
        session=db_session,
        organiser_id=organiser.id,
        page=99,
        limit=20,
    )

    assert total == 1
    assert templates == []


@pytest.fixture
async def template_with_logo(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> Badge:
    template = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Event With Logo",
        canvas_data={"layout_id": "v1"},
        logo_url="https://res.cloudinary.com/mycloud/image/upload/template-logos/logo-abc.png",
        logo_public_id="template-logos/logo-abc",
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def bare_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> Badge:
    """Template with no logo and no badges."""
    template = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Bare Event",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_removes_template_from_db(
    _mock_delete: AsyncMock,
    db_session: AsyncSession,
    organiser: User,
    bare_template: Badge,
) -> None:
    id = bare_template.id

    await delete_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=id,
    )

    result = await db_session.get(Badge, id)
    assert result is None


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_cascades_hashtags_from_db(
    _mock_delete: AsyncMock,
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    template = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Tagged Event",
        canvas_data={"layout_id": "v1"},
    )
    db_session.add(template)
    await db_session.flush()
    db_session.add(BadgeHashtag(badge_id=template.id, hashtag="#DeleteMe"))
    await db_session.commit()
    await db_session.refresh(template)

    id = template.id
    await delete_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=id,
    )

    result = await db_session.execute(
        select(BadgeHashtag).where(BadgeHashtag.badge_id == id)
    )
    assert result.scalars().all() == []


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_calls_cloudinary_for_logo(
    mock_delete_logo: AsyncMock,
    db_session: AsyncSession,
    organiser: User,
    template_with_logo: Badge,
) -> None:
    await delete_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=template_with_logo.id,
    )

    mock_delete_logo.assert_awaited_once_with("template-logos/logo-abc")


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_skips_logo_cleanup_when_no_logo(
    mock_delete_logo: AsyncMock,
    db_session: AsyncSession,
    organiser: User,
    bare_template: Badge,
) -> None:
    await delete_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=bare_template.id,
    )

    mock_delete_logo.assert_not_called()


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_continues_when_logo_cloudinary_fails(
    mock_delete_logo: AsyncMock,
    db_session: AsyncSession,
    organiser: User,
    template_with_logo: Badge,
) -> None:
    mock_delete_logo.side_effect = Exception("Cloudinary unavailable")
    id = template_with_logo.id

    # Must not raise
    await delete_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=id,
    )

    # Template is gone from DB despite Cloudinary failure
    result = await db_session.get(Badge, id)
    assert result is None


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_raises_not_found_for_missing_template(
    _mock: AsyncMock,
    db_session: AsyncSession,
    organiser: User,
) -> None:
    import uuid

    with pytest.raises(BadgeNotFoundError):
        await delete_badge(
            session=db_session,
            organiser_id=organiser.id,
            id=uuid.uuid4(),
        )


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_raises_not_found_for_soft_deleted_template(
    _mock: AsyncMock,
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    soft_deleted = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Soft Deleted",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(soft_deleted)
    await db_session.commit()
    await db_session.refresh(soft_deleted)

    with pytest.raises(BadgeNotFoundError):
        await delete_badge(
            session=db_session,
            organiser_id=organiser.id,
            id=soft_deleted.id,
        )


@patch("app.services.badge.delete_logo", new_callable=AsyncMock)
async def test_delete_raises_not_owner(
    _mock: AsyncMock,
    db_session: AsyncSession,
    bare_template: Badge,
) -> None:
    import uuid

    with pytest.raises(NotBadgeOwnerError):
        await delete_badge(
            session=db_session,
            organiser_id=uuid.uuid4(),
            id=bare_template.id,
        )


@pytest.fixture
async def editable_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> Badge:
    template = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Original Title",
        canvas_data={"layout_id": "v1", "accent": "#000000"},
        default_caption="Original caption",
        destination_link="https://original.example.com",
        thumbnail_url="https://cdn.example.com/original.png",
        access_type=0,
    )
    db_session.add(template)
    await db_session.flush()

    for tag in ["#Original", "#Event"]:
        db_session.add(BadgeHashtag(badge_id=template.id, hashtag=tag))

    await db_session.commit()
    await db_session.refresh(template)
    return template


async def _call_edit(
    db_session: AsyncSession,
    organiser: User,
    template: Badge,
    field_updates: dict[str, Any],
    new_hashtags: list[str] | None = None,
    update_hashtags: bool = False,
) -> Badge:
    return await edit_badge(
        session=db_session,
        organiser_id=organiser.id,
        id=template.id,
        field_updates=field_updates,
        new_hashtags=new_hashtags,
        update_hashtags=update_hashtags,
    )


async def test_edit_updates_title(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    result = await _call_edit(
        db_session, organiser, editable_template, {"title": "New Title"}
    )

    assert result.title == "New Title"


async def test_edit_updates_canvas_data(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    new_canvas = {"layout_id": "v2", "accent": "#FF0000"}
    result = await _call_edit(
        db_session, organiser, editable_template, {"canvas_data": new_canvas}
    )

    assert result.canvas_data == new_canvas


async def test_edit_updates_multiple_fields_at_once(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    result = await _call_edit(
        db_session,
        organiser,
        editable_template,
        {
            "title": "Multi Update",
            "default_caption": "New caption",
            "destination_link": "https://new.example.com",
        },
    )

    assert result.title == "Multi Update"
    assert result.default_caption == "New caption"
    assert result.destination_link == "https://new.example.com"


async def test_edit_leaves_unset_fields_unchanged(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    original_canvas = editable_template.canvas_data
    original_caption = editable_template.default_caption

    await _call_edit(
        db_session, organiser, editable_template, {"title": "Only Title Changed"}
    )

    refreshed = await db_session.get(Badge, editable_template.id)
    assert refreshed is not None
    assert refreshed.canvas_data == original_canvas
    assert refreshed.default_caption == original_caption


async def test_edit_clears_nullable_field_when_sent_as_none(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    result = await _call_edit(
        db_session, organiser, editable_template, {"default_caption": None}
    )

    assert result.default_caption is None


async def test_edit_persists_changes_to_database(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    await _call_edit(
        db_session, organiser, editable_template, {"title": "Persisted Title"}
    )

    stored = await db_session.get(Badge, editable_template.id)
    assert stored is not None
    assert stored.title == "Persisted Title"


async def test_edit_replaces_hashtags_when_provided(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    result = await _call_edit(
        db_session,
        organiser,
        editable_template,
        {},
        new_hashtags=["#NewTag", "#Another"],
        update_hashtags=True,
    )

    tags = sorted(tag.hashtag for tag in result.hashtags)
    assert tags == ["#Another", "#NewTag"]


async def test_edit_clears_hashtags_when_empty_list_provided(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    result = await _call_edit(
        db_session,
        organiser,
        editable_template,
        {},
        new_hashtags=[],
        update_hashtags=True,
    )

    assert result.hashtags == []


async def test_edit_leaves_hashtags_unchanged_when_key_omitted(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    await _call_edit(
        db_session,
        organiser,
        editable_template,
        {"title": "Title Only"},
        update_hashtags=False,
    )

    stored_tags = await db_session.execute(
        select(BadgeHashtag).where(BadgeHashtag.badge_id == editable_template.id)
    )
    tags = sorted(t.hashtag for t in stored_tags.scalars().all())
    assert tags == ["#Event", "#Original"]


async def test_edit_returns_template_with_hashtags_loaded(
    db_session: AsyncSession,
    organiser: User,
    editable_template: Badge,
) -> None:
    result = await _call_edit(
        db_session,
        organiser,
        editable_template,
        {},
        new_hashtags=["#Loaded"],
        update_hashtags=True,
    )

    # Relationship must be accessible without triggering lazy load errors.
    assert isinstance(result.hashtags, list)
    assert len(result.hashtags) == 1


async def test_edit_raises_not_found_for_missing_template(
    db_session: AsyncSession,
    organiser: User,
) -> None:
    with pytest.raises(BadgeNotFoundError):
        await edit_badge(
            session=db_session,
            organiser_id=organiser.id,
            id=uuid.uuid4(),
            field_updates={"title": "Ghost"},
            new_hashtags=None,
            update_hashtags=False,
        )


async def test_edit_raises_not_found_for_soft_deleted_template(
    db_session: AsyncSession,
    organiser: User,
    platform_template: PlatformTemplate,
) -> None:
    from datetime import UTC, datetime

    soft_deleted = Badge(
        organiser_id=organiser.id,
        platform_template_id=platform_template.id,
        title="Gone",
        canvas_data={"layout_id": "v1"},
        deleted_at=datetime.now(UTC),
    )
    db_session.add(soft_deleted)
    await db_session.commit()
    await db_session.refresh(soft_deleted)

    with pytest.raises(BadgeNotFoundError):
        await edit_badge(
            session=db_session,
            organiser_id=organiser.id,
            id=soft_deleted.id,
            field_updates={"title": "Attempt"},
            new_hashtags=None,
            update_hashtags=False,
        )


async def test_edit_raises_not_owner(
    db_session: AsyncSession,
    editable_template: Badge,
) -> None:
    with pytest.raises(NotBadgeOwnerError):
        await edit_badge(
            session=db_session,
            organiser_id=uuid.uuid4(),
            id=editable_template.id,
            field_updates={"title": "Hijacked"},
            new_hashtags=None,
            update_hashtags=False,
        )
