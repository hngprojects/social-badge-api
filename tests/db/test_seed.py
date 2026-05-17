import logging
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import seed
from app.db.seed import (
    PLATFORM_TEMPLATES_SEED,
    main,
    seed_platform_templates,
)
from app.models import PlatformTemplate


class _SessionContext:
    """Wrap an AsyncSession so it can be used as `async with` without closing it.

    The test fixture owns the session lifecycle; the seed function calls
    `AsyncSessionLocal()` and uses the result as an async context manager.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture
def patched_session_local(db_session: AsyncSession):
    def factory() -> _SessionContext:
        return _SessionContext(db_session)

    with patch.object(seed, "AsyncSessionLocal", factory):
        yield


def test_platform_templates_seed_has_four_entries() -> None:
    assert len(PLATFORM_TEMPLATES_SEED) == 4


def test_platform_templates_seed_titles_are_unique() -> None:
    titles = [t["title"] for t in PLATFORM_TEMPLATES_SEED]
    assert len(set(titles)) == len(titles)


def test_platform_templates_seed_entries_have_required_keys() -> None:
    expected_keys = {"title", "canvas_data", "thumbnail_url"}
    for entry in PLATFORM_TEMPLATES_SEED:
        assert set(entry.keys()) == expected_keys
        assert isinstance(entry["title"], str) and entry["title"]
        assert isinstance(entry["canvas_data"], dict)
        assert "layout" in entry["canvas_data"]


@pytest.mark.usefixtures("patched_session_local")
async def test_seed_platform_templates_inserts_all_entries(
    db_session: AsyncSession,
) -> None:
    await seed_platform_templates()

    result = await db_session.execute(select(PlatformTemplate))
    templates = result.scalars().all()

    assert len(templates) == len(PLATFORM_TEMPLATES_SEED)
    inserted_titles = sorted(t.title for t in templates)
    expected_titles = sorted(t["title"] for t in PLATFORM_TEMPLATES_SEED)
    assert inserted_titles == expected_titles


@pytest.mark.usefixtures("patched_session_local")
async def test_seed_platform_templates_persists_canvas_data(
    db_session: AsyncSession,
) -> None:
    await seed_platform_templates()

    result = await db_session.execute(select(PlatformTemplate))
    templates = {t.title: t for t in result.scalars().all()}

    for entry in PLATFORM_TEMPLATES_SEED:
        stored = templates[entry["title"]]
        assert stored.canvas_data == entry["canvas_data"]
        assert stored.thumbnail_url == entry["thumbnail_url"]


@pytest.mark.usefixtures("patched_session_local")
async def test_seed_platform_templates_is_idempotent(
    db_session: AsyncSession,
) -> None:
    await seed_platform_templates()
    await seed_platform_templates()

    result = await db_session.execute(select(PlatformTemplate))
    templates = result.scalars().all()

    assert len(templates) == len(PLATFORM_TEMPLATES_SEED)


@pytest.mark.usefixtures("patched_session_local")
async def test_seed_platform_templates_inserts_only_missing_titles(
    db_session: AsyncSession,
) -> None:
    pre_existing_canvas = {"layout": "custom-creative"}
    db_session.add(
        PlatformTemplate(
            title="Creative",
            canvas_data=pre_existing_canvas,
            thumbnail_url=None,
        )
    )
    await db_session.commit()

    await seed_platform_templates()

    result = await db_session.execute(select(PlatformTemplate))
    templates = {t.title: t for t in result.scalars().all()}

    assert len(templates) == len(PLATFORM_TEMPLATES_SEED)
    assert templates["Creative"].canvas_data == pre_existing_canvas
    for entry in PLATFORM_TEMPLATES_SEED:
        if entry["title"] == "Creative":
            continue
        assert templates[entry["title"]].canvas_data == entry["canvas_data"]


@pytest.mark.usefixtures("patched_session_local")
async def test_seed_platform_templates_logs_when_already_seeded(
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    for entry in PLATFORM_TEMPLATES_SEED:
        db_session.add(PlatformTemplate(**entry))
        await db_session.flush()
    await db_session.commit()

    with caplog.at_level(logging.INFO, logger="app.db.seed"):
        await seed_platform_templates()

    assert any(
        "already seeded" in record.message for record in caplog.records
    )


@pytest.mark.usefixtures("patched_session_local")
async def test_seed_platform_templates_logs_count_on_insert(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.db.seed"):
        await seed_platform_templates()

    assert any(
        "Seeded" in record.message
        and str(len(PLATFORM_TEMPLATES_SEED)) in record.message
        for record in caplog.records
    )


async def test_main_invokes_seed_platform_templates() -> None:
    with patch.object(
        seed, "seed_platform_templates", new_callable=AsyncMock
    ) as mock_seed:
        await main()

    mock_seed.assert_awaited_once()
