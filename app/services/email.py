import asyncio
import html
import logging
from datetime import datetime
from email.message import EmailMessage

import aiosmtplib
import resend
import resend.exceptions

from app.core.config import settings
from app.core.exceptions import EmailDeliveryError
from app.services import email_templates

logger = logging.getLogger(__name__)

resend.api_key = settings.RESEND_API_KEY


def _build_verification_html(token: str) -> str:
    action_url = f"{settings.FRONTEND_URL}/verify?token={token}"
    return email_templates.render(
        "verification",
        action_url=action_url,
        expires_minutes=str(settings.VERIFICATION_TOKEN_TTL_MINUTES),
    )


def _build_account_lock_html() -> str:
    minutes = settings.LOCKOUT_WINDOW // 60
    return email_templates.render(
        "account_lock",
        minutes=str(minutes),
    )


def _build_password_reset_html(token: str) -> str:
    action_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    return email_templates.render(
        "password_reset",
        action_url=action_url,
        expires_minutes=str(settings.PASSWORD_RESET_TOKEN_TTL_MINUTES),
    )


def _build_onboarding_html() -> str:
    action_url = f"{settings.FRONTEND_URL}/dashboard"
    return email_templates.render(
        "onboarding",
        action_url=action_url,
    )


def _build_notification_html(
    *,
    reference_id: str,
    first_name: str,
    last_name: str | None,
    email: str,
    subject: str,
    message: str,
) -> str:
    escaped_full_name = html.escape(f"{first_name} {last_name}".strip() if last_name else first_name)
    escaped_email = html.escape(email)
    escaped_subject = html.escape(subject)
    escaped_message = html.escape(message)
    return email_templates.render(
        "notification",
        reference_id=reference_id,
        escaped_full_name=escaped_full_name,
        escaped_email=escaped_email,
        escaped_subject=escaped_subject,
        escaped_message=escaped_message,
    )


def _build_confirmation_html(
    *,
    first_name: str,
    reference_id: str,
) -> str:
    """HTML confirmation email sent to the person who submitted the contact form."""
    safe_name = html.escape(first_name)
    return email_templates.render(
        "confirmation",
        safe_name=safe_name,
        reference_id=reference_id,
    )


def _build_security_alert_html(detected_at: datetime) -> str:
    formatted_time = detected_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    return email_templates.render(
        "security_alert",
        formatted_time=formatted_time,
    )


async def _send_smtp_email(
    *,
    to: str | list[str],
    subject: str,
    html_content: str,
    reply_to: str | None = None,
) -> None:
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to if isinstance(to, str) else ", ".join(to)
    message["Subject"] = subject
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info("Email successfully delivered via SMTP fallback to %s", to)
    except Exception as exc:
        logger.exception("SMTP fallback failed for %s", to)
        raise EmailDeliveryError(f"SMTP fallback failed for {to}") from exc


async def send_verification_email(to: str, token: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.VERIFICATION_SUBJECT,
        "html": _build_verification_html(token),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for verification email to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.VERIFICATION_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending verification email to %s", to)
        raise EmailDeliveryError(f"Failed to send verification email to {to}") from exc


async def send_account_lock_email(to: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.ACCOUNT_LOCK_SUBJECT,
        "html": _build_account_lock_html(),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for account lock email to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.ACCOUNT_LOCK_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending account lock email to %s", to)
        raise EmailDeliveryError(f"Failed to send account lock email to {to}") from exc


async def send_password_reset_email(to: str, token: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.PASSWORD_RESET_SUBJECT,
        "html": _build_password_reset_html(token),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for password reset email to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.PASSWORD_RESET_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending password reset email to %s", to)
        raise EmailDeliveryError(
            f"Failed to send password reset email to {to}"
        ) from exc


async def send_onboarding_email(to: str) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.ONBOARDING_SUBJECT,
        "html": _build_onboarding_html(),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for onboarding email to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.ONBOARDING_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending onboarding email to %s", to)
        raise EmailDeliveryError(f"Failed to send onboarding email to {to}") from exc


async def send_security_alert_email(to: str, detected_at: datetime) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to],
        "subject": settings.SECURITY_ALERT_SUBJECT,
        "html": _build_security_alert_html(detected_at),
    }

    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for security alert to %s, trying SMTP fallback", to
        )
        await _send_smtp_email(
            to=to,
            subject=settings.SECURITY_ALERT_SUBJECT,
            html_content=params["html"],
        )
    except Exception as exc:
        logger.exception("Unexpected error sending security alert to %s", to)
        raise EmailDeliveryError(f"Failed to send security alert to {to}") from exc


async def send_contact_notification(
    *,
    reference_id: str,
    first_name: str,
    last_name: str | None,
    email: str,
    subject: str,
    message: str,
) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [settings.CONTACT_RECIPIENT_EMAIL],
        "reply_to": email,
        "subject": settings.CONTACT_NOTIFICATION_SUBJECT,
        "html": _build_notification_html(
            reference_id=reference_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            subject=subject,
            message=message,
        ),
    }
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for contact notification (ref %s), trying SMTP fallback",
            reference_id,
        )
        await _send_smtp_email(
            to=settings.CONTACT_RECIPIENT_EMAIL,
            subject=settings.CONTACT_NOTIFICATION_SUBJECT,
            html_content=params["html"],
            reply_to=email,
        )
    except Exception as exc:
        logger.exception(
            "Unexpected error sending contact notification for ref %s", reference_id
        )
        raise EmailDeliveryError(
            f"Failed to send contact notification for {reference_id}"
        ) from exc


async def send_contact_confirmation(
    *,
    to_email: str,
    first_name: str,
    reference_id: str,
) -> None:
    params: resend.Emails.SendParams = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [to_email],
        "subject": settings.CONTACT_CONFIRMATION_SUBJECT,
        "html": _build_confirmation_html(
            first_name=first_name,
            reference_id=reference_id,
        ),
    }
    try:
        await asyncio.to_thread(resend.Emails.send, params)
    except resend.exceptions.ResendError:
        logger.warning(
            "Resend failed for contact confirmation to %s (ref %s), "
            "trying SMTP fallback",
            to_email,
            reference_id,
        )
        try:
            await _send_smtp_email(
                to=to_email,
                subject=settings.CONTACT_CONFIRMATION_SUBJECT,
                html_content=params["html"],
            )
        except Exception:
            logger.exception(
                "Final failure: SMTP fallback also failed for contact "
                "confirmation to %s (ref %s)",
                to_email,
                reference_id,
            )
    except Exception:
        logger.exception(
            "Unexpected error sending contact confirmation to %s (ref %s)",
            to_email,
            reference_id,
        )
