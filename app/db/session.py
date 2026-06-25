from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(str(settings.DATABASE_URL), echo=False)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Asynchronously generates and manages an SQLAlchemy database session.

    Yields a database session instance, automatically closing it upon completion or when
    an exception occurs inside the generator context.
    """

    async with AsyncSessionLocal() as session:
        yield session
