import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Must be set before app imports: Settings() is constructed at import time
# and raises ValidationError if SECRET_KEY is missing.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production")
os.environ["COOKIE_SECURE"] = "False"  # Disable secure cookies for HTTP tests
os.environ["COOKIE_SAMESITE"] = "lax"  # Use lax samesite for tests
os.environ["COOKIE_DOMAIN"] = ""  # Keep auth cookies host-only in tests

from app.core.config import settings
from app.db.redis import get_redis_client
from app.db.session import get_session
from app.main import app  # noqa: E402

# Import all models to ensure they're registered with Base.metadata
from app.models.base import Base


def create_db_engine() -> AsyncEngine:
    url = make_url(str(settings.DATABASE_URL))
    # Force the use of the 'test' database to avoid dropping main database tables.
    if url.database != "test":
        url = url.set(database="test")
    db_url = url.render_as_string(hide_password=False)

    test_engine = create_async_engine(
        db_url,
        poolclass=NullPool,
    )
    return test_engine


@pytest.fixture(scope="session")
async def setup_db() -> AsyncIterator[None]:
    # Create all tables in the test database
    test_engine = create_db_engine()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def db_session(setup_db: None) -> AsyncIterator[AsyncSession]:
    test_engine = create_db_engine()

    TestingSessionLocal = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())

    await test_engine.dispose()


@pytest.fixture
def fake_redis() -> FakeAsyncRedis:
    return FakeAsyncRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def reset_limiter() -> None:
    from app.core.rate_limit import limiter

    limiter.reset()


@pytest.fixture
async def client(
    db_session: AsyncSession, fake_redis: FakeAsyncRedis
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def override_get_redis() -> AsyncIterator[FakeAsyncRedis]:
        yield fake_redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_redis_client] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        original_request = async_client.request

        async def custom_request(*args: Any, **kwargs: Any) -> Any:
            cookies = kwargs.pop("cookies", None)
            if cookies:
                old_cookies = dict(async_client.cookies)
                async_client.cookies.clear()
                async_client.cookies.update(cookies)
                try:
                    return await original_request(*args, **kwargs)
                finally:
                    async_client.cookies.clear()
                    async_client.cookies.update(old_cookies)
            return await original_request(*args, **kwargs)

        async_client.request = custom_request  # type: ignore[method-assign]
        yield async_client

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_redis_client, None)


@pytest.fixture
def valid_signup_payload() -> dict[str, str]:
    return {
        "first_name": "API Test",
        "last_name": "User",
        "email": "apitest@example.com",
        "password": "StrongPassword1!",  # noqa: S106
    }
