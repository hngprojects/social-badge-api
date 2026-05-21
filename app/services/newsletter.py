import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.newsletter import NewsletterSubscriber
from app.services.email import send_newsletter_welcome_email

logger = logging.getLogger(__name__)


def _make_unsubscribe_token() -> str:
    return secrets.token_hex(32)


async def subscribe(
    session: AsyncSession,
    email: str,
) -> tuple[NewsletterSubscriber, bool]:
    """Subscribe an email to the newsletter.

    Returns ``(subscriber, created)`` where *created* is ``True`` for a new or
    reactivated subscription and ``False`` when already active.  A welcome email
    is sent (best-effort) whenever *created* is ``True``.
    """
    result = await session.execute(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == email)
    )
    subscriber = result.scalar_one_or_none()

    if subscriber is not None and subscriber.is_active:
        return subscriber, False

    if subscriber is None:
        subscriber = NewsletterSubscriber(
            email=email,
            unsubscribe_token=_make_unsubscribe_token(),
        )
        session.add(subscriber)
    else:
        # Reactivate a previously unsubscribed address.
        subscriber.is_active = True
        subscriber.unsubscribe_token = _make_unsubscribe_token()
        subscriber.unsubscribed_at = None

    await session.commit()
    await session.refresh(subscriber)

    try:
        await send_newsletter_welcome_email(
            to=email,
            unsubscribe_token=subscriber.unsubscribe_token,
        )
    except Exception:
        logger.exception("Failed to send newsletter welcome email to %s", email)

    return subscriber, True


async def unsubscribe(session: AsyncSession, token: str) -> bool:
    """Unsubscribe by token.

    Returns ``True`` if the token was found (regardless of prior active state)
    and ``False`` if the token does not exist.
    """
    result = await session.execute(
        select(NewsletterSubscriber).where(
            NewsletterSubscriber.unsubscribe_token == token
        )
    )
    subscriber = result.scalar_one_or_none()

    if subscriber is None:
        return False

    if subscriber.is_active:
        subscriber.is_active = False
        subscriber.unsubscribed_at = datetime.now(UTC)
        await session.commit()

    return True
