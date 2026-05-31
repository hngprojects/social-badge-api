import pytest
from pydantic import ValidationError

from app.schemas.profile import ChangePasswordRequest


def test_valid_payload_is_accepted() -> None:
    req = ChangePasswordRequest(
        current_password="OldPassword1!",  # noqa: S106
        new_password="NewPassword1!",  # noqa: S106
        confirm_password="NewPassword1!",  # noqa: S106
    )
    assert req.current_password == "OldPassword1!"  # noqa: S105
    assert req.new_password == "NewPassword1!"  # noqa: S105
    assert req.confirm_password == "NewPassword1!"  # noqa: S105


def test_missing_current_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChangePasswordRequest(
            new_password="NewPassword1!",
            confirm_password="NewPassword1!",
        )


def test_missing_new_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChangePasswordRequest(
            current_password="OldPassword1!",
            confirm_password="NewPassword1!",
        )


def test_missing_confirm_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChangePasswordRequest(
            current_password="OldPassword1!",
            new_password="NewPassword1!",
        )


def test_current_password_over_500_bytes_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not exceed 500 bytes"):
        ChangePasswordRequest(
            current_password="A" * 501,
            new_password="NewPassword1!",  # noqa: S106
            confirm_password="NewPassword1!",  # noqa: S106
        )


def test_current_password_at_500_bytes_is_accepted() -> None:
    req = ChangePasswordRequest(
        current_password="A" * 500,
        new_password="NewPassword1!",  # noqa: S106
        confirm_password="NewPassword1!",  # noqa: S106
    )
    assert len(req.current_password) == 500


@pytest.mark.parametrize(
    ("new_password", "expected_fragment"),
    [
        ("short1!", "at least 8 characters"),
        ("nouppercase1!", "uppercase"),
        ("NOLOWERCASE1!", "lowercase"),
        ("NoNumbers!!", "one number"),
        ("NoSpecialChar1", "special character"),
    ],
)
def test_weak_new_password_is_rejected(
    new_password: str, expected_fragment: str
) -> None:
    with pytest.raises(ValidationError, match=expected_fragment):
        ChangePasswordRequest(
            current_password="OldPassword1!",  # noqa: S106
            new_password=new_password,
            confirm_password=new_password,
        )


def test_new_password_over_500_bytes_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not exceed 500 bytes"):
        ChangePasswordRequest(
            current_password="OldPassword1!",  # noqa: S106
            new_password="A" * 501,
            confirm_password="A" * 501,
        )


def test_mismatched_confirm_password_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Passwords do not match"):
        ChangePasswordRequest(
            current_password="OldPassword1!",  # noqa: S106
            new_password="NewPassword1!",  # noqa: S106
            confirm_password="DifferentPassword1!",  # noqa: S106
        )


def test_new_password_same_as_current_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must differ from the current password"):
        ChangePasswordRequest(
            current_password="SamePassword1!",  # noqa: S106
            new_password="SamePassword1!",  # noqa: S106
            confirm_password="SamePassword1!",  # noqa: S106
        )


def test_mismatch_error_reported_before_same_as_current_check() -> None:
    """When new != confirm AND new == current, mismatch is reported first."""
    with pytest.raises(ValidationError, match="Passwords do not match"):
        ChangePasswordRequest(
            current_password="Password1!",  # noqa: S106
            new_password="Password1!",  # noqa: S106
            confirm_password="DifferentPassword1!",  # noqa: S106
        )
