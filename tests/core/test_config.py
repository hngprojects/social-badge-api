import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_allowed_origins_parsing_comma_separated() -> None:
    settings = Settings(
        SECRET_KEY="test-secret",  # noqa: S106
        DATABASE_URL="postgresql+asyncpg://postgres:root@127.0.0.1:5432/test",  # type: ignore[arg-type]
        ALLOWED_ORIGINS="http://localhost:3000, http://localhost:5000",
    )
    assert settings.ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "http://localhost:5000",
    ]


def test_allowed_origins_parsing_json_list() -> None:
    settings = Settings(
        SECRET_KEY="test-secret",  # noqa: S106
        DATABASE_URL="postgresql+asyncpg://postgres:root@127.0.0.1:5432/test",  # type: ignore[arg-type]
        ALLOWED_ORIGINS='["http://localhost:3000", "http://localhost:5000"]',
    )
    # pydantic-settings should have decoded this into a list before the validator
    assert settings.ALLOWED_ORIGINS == [
        "http://localhost:3000",
        "http://localhost:5000",
    ]


def test_allowed_origins_parsing_invalid_type() -> None:
    with pytest.raises(ValidationError):
        Settings(
            SECRET_KEY="test-secret",  # noqa: S106
            DATABASE_URL="postgresql+asyncpg://postgres:root@127.0.0.1:5432/test",  # type: ignore[arg-type]
            ALLOWED_ORIGINS=123,  # type: ignore
        )
