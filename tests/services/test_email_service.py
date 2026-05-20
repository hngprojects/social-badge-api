from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import resend
import resend.exceptions

from app.core.config import settings
from app.core.exceptions import EmailDeliveryError
from app.services.email import (
    send_account_lock_email,
    send_security_alert_email,
    send_verification_email,
)


@patch("app.services.email.resend.Emails.send")
async def test_sends_email_with_correct_params(mock_send: MagicMock) -> None:
    mock_send.return_value = {"id": "test-id"}

    await send_verification_email("user@example.com", "test-token")

    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert call_args["to"] == ["user@example.com"]
    assert "test-token" in call_args["html"]
    assert call_args["subject"] == "Verify your Flare Tag account"


@patch("app.services.email.resend.Emails.send")
@patch("app.services.email._send_smtp_email")
async def test_raises_email_delivery_error_on_failure(
    mock_smtp_send: MagicMock,
    mock_send: MagicMock,
) -> None:
    mock_send.side_effect = resend.exceptions.ResendError(
        "API error", "error_type", "400", "suggested action"
    )
    mock_smtp_send.side_effect = EmailDeliveryError("SMTP fallback failed")

    with pytest.raises(EmailDeliveryError):
        await send_verification_email("user@example.com", "test-token")


# ---------------------------------------------------------------------------
# send_account_lock_email tests
# ---------------------------------------------------------------------------


@patch("app.services.email.resend.Emails.send")
async def test_sends_account_lock_email_with_correct_params(
    mock_send: MagicMock,
) -> None:
    mock_send.return_value = {"id": "lock-id"}

    await send_account_lock_email("user@example.com")

    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert call_args["to"] == ["user@example.com"]
    assert call_args["subject"] == "Your Flare Tag account has been locked"
    assert "locked" in call_args["html"].lower()


@patch("app.services.email.resend.Emails.send")
@patch("app.services.email._send_smtp_email")
async def test_account_lock_email_raises_on_failure(
    mock_smtp_send: MagicMock,
    mock_send: MagicMock,
) -> None:
    mock_send.side_effect = resend.exceptions.ResendError(
        "API error", "error_type", "400", "suggested action"
    )
    mock_smtp_send.side_effect = EmailDeliveryError("SMTP fallback failed")

    with pytest.raises(EmailDeliveryError):
        await send_account_lock_email("user@example.com")


# ---------------------------------------------------------------------------
# send_security_alert_email tests
# ---------------------------------------------------------------------------


@patch("app.services.email.resend.Emails.send")
async def test_security_alert_email_correct_params(mock_send: MagicMock) -> None:
    mock_send.return_value = {"id": "alert-id"}
    detected_at = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

    await send_security_alert_email("user@example.com", detected_at)

    mock_send.assert_called_once()
    call_args = mock_send.call_args[0][0]
    assert call_args["to"] == ["user@example.com"]
    assert call_args["subject"] == settings.SECURITY_ALERT_SUBJECT
    assert "2026-05-19" in call_args["html"]
    assert "sessions" in call_args["html"].lower()


@patch("app.services.email.resend.Emails.send")
@patch("app.services.email._send_smtp_email", new_callable=AsyncMock)
async def test_security_alert_email_smtp_fallback_on_resend_error(
    mock_smtp: AsyncMock,
    mock_send: MagicMock,
) -> None:
    mock_send.side_effect = resend.exceptions.ResendError(
        "API error", "error_type", "400", "suggested action"
    )
    detected_at = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

    await send_security_alert_email("user@example.com", detected_at)

    mock_smtp.assert_called_once()
    smtp_kwargs = mock_smtp.call_args.kwargs
    assert smtp_kwargs["to"] == "user@example.com"
    assert smtp_kwargs["subject"] == settings.SECURITY_ALERT_SUBJECT
    assert "2026-05-19" in smtp_kwargs["html_content"]


@patch("app.services.email.resend.Emails.send")
async def test_security_alert_email_raises_on_unexpected_exception(
    mock_send: MagicMock,
) -> None:
    mock_send.side_effect = RuntimeError("Unexpected error")
    detected_at = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)

    with pytest.raises(EmailDeliveryError):
        await send_security_alert_email("user@example.com", detected_at)


def test_email_template_renders_without_double_slashes() -> None:
    from app.services import email_templates
    html = email_templates.render("verification", action_url="http://localhost:3000/verify", expires_minutes="30", frontend_url="https://flaretag.com/")
    assert "https://flaretag.com/privacy" in html
    assert "https://flaretag.com//privacy" not in html
