import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InvalidCredentialsError,
)
from app.core.security import hash_password
from app.models import User
from app.schemas.profile import ChangePasswordRequest
from app.services.profile import change_password


async def _create_user(
    session: AsyncSession,
    email: str,
    password: str = "OldPassword1!",  # noqa: S107
    has_password: bool = True,
) -> User:
    user = User(
        first_name="Change",
        last_name="Password",
        email=email,
        password_hash=hash_password(password) if has_password else None,
        is_email_verified=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _payload(
    current: str = "OldPassword1!",
    new: str = "NewPassword1!",
    confirm: str = "NewPassword1!",
) -> ChangePasswordRequest:
    return ChangePasswordRequest(
        current_password=current,
        new_password=new,
        confirm_password=confirm,
    )


async def test_oauth_only_account_raises_invalid_credentials(
    db_session: AsyncSession,
    fake_redis: FakeAsyncRedis,
) -> None:
    user = await _create_user(db_session, "cp-oauth@example.com", has_password=False)

    with pytest.raises(InvalidCredentialsError):
        await change_password(
            db_session,
            fake_redis,
            user,
            _payload(),
            access_token=None,
        )


async def test_oauth_only_account_hash_remains_none(
    db_session: AsyncSession,
    fake_redis: FakeAsyncRedis,
) -> None:
    user = await _create_user(
        db_session, "cp-oauth-hash@example.com", has_password=False
    )

    with pytest.raises(InvalidCredentialsError):
        await change_password(
            db_session,
            fake_redis,
            user,
            _payload(),
            access_token=None,
        )

    await db_session.refresh(user)
    assert user.password_hash is None
