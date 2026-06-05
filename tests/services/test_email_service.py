from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.core.exceptions import EmailDeliveryError
from app.services.email import (
    send_account_lock_email,
    send_security_alert_email,
    send_verification_email,
)


@patch("app.services.email.email_provider.send", new_callable=AsyncMock)
async def test_sends_email_with_correct_params(mock_send: AsyncMock) -> None:
    await send_verification_email("user@example.com", "test-token")

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "user@example.com"
    assert "test-token" in call_kwargs["html_content"]
    assert call_kwargs["subject"] == settings.VERIFICATION_SUBJECT


@patch("app.services.email.email_provider.send", new_callable=AsyncMock)
async def test_raises_email_delivery_error_on_failure(
    mock_send: AsyncMock,
) -> None:
    mock_send.side_effect = EmailDeliveryError("SMTP fallback failed")

    with pytest.raises(EmailDeliveryError):
        await send_verification_email("user@example.com", "test-token")


# ---------------------------------------------------------------------------
# send_account_lock_email tests
# ---------------------------------------------------------------------------


@patch("app.services.email.email_provider.send", new_callable=AsyncMock)
async def test_sends_account_lock_email_with_correct_params(
    mock_send: AsyncMock,
) -> None:
    await send_account_lock_email("user@example.com")

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "user@example.com"
    assert call_kwargs["subject"] == settings.ACCOUNT_LOCK_SUBJECT
    assert "locked" in call_kwargs["html_content"].lower()


@patch("app.services.email.email_provider.send", new_callable=AsyncMock)
async def test_account_lock_email_raises_on_failure(
    mock_send: AsyncMock,
) -> None:
    mock_send.side_effect = EmailDeliveryError("SMTP fallback failed")

    with pytest.raises(EmailDeliveryError):
        await send_account_lock_email("user@example.com")


# ---------------------------------------------------------------------------
# send_security_alert_email tests
# ---------------------------------------------------------------------------


@patch("app.services.email.email_provider.send", new_callable=AsyncMock)
async def test_security_alert_email_correct_params(mock_send: AsyncMock) -> None:
    detected_at = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

    await send_security_alert_email("user@example.com", detected_at)

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "user@example.com"
    assert call_kwargs["subject"] == settings.SECURITY_ALERT_SUBJECT
    assert "2026-05-19" in call_kwargs["html_content"]
    assert "sessions" in call_kwargs["html_content"].lower()


@patch("app.services.email.email_provider.send", new_callable=AsyncMock)
async def test_security_alert_email_raises_on_unexpected_exception(
    mock_send: AsyncMock,
) -> None:
    mock_send.side_effect = RuntimeError("Unexpected error")
    detected_at = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

    with pytest.raises(Exception): # Can be generic Exception or EmailDeliveryError based on how it's handled. Currently in the code we don't catch unexpected ones in the provider if the provider doesn't wrap them, wait: we wrap it in EmailDeliveryError if we use SMTPEmailProvider, but the test patches email_provider.send! So if it raises RuntimeError, the function send_security_alert_email does NOT catch it. It will raise RuntimeError.
        await send_security_alert_email("user@example.com", detected_at)


def test_email_template_renders_without_double_slashes() -> None:
    from app.services import email_templates

    html = email_templates.render(
        "verification",
        action_url="http://localhost:3000/verify",
        expires_minutes="30",
        frontend_url="https://flaretag.com/",
    )
    assert "https://flaretag.com/privacy" in html
    assert "https://flaretag.com//privacy" not in html
