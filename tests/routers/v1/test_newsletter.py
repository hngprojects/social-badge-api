from unittest.mock import AsyncMock, patch

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.newsletter import NewsletterSubscriber

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _subscribe(client: AsyncClient, email: str) -> Response:
    response = await client.post(
        "/api/v1/newsletter/subscribe",
        json={"email": email},
    )
    return response


# ---------------------------------------------------------------------------
# Subscribe tests
# ---------------------------------------------------------------------------


async def test_subscribe_success(client: AsyncClient) -> None:
    with patch(
        "app.services.newsletter.send_newsletter_welcome_email",
        new_callable=AsyncMock,
    ):
        response = await _subscribe(client, "user@example.com")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "subscribed" in data["message"].lower()
    assert data["data"]["email"] == "user@example.com"
    assert data["data"]["subscribed_at"] is not None


async def test_subscribe_already_active_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    with patch(
        "app.services.newsletter.send_newsletter_welcome_email",
        new_callable=AsyncMock,
    ) as mock_email:
        await _subscribe(client, "dup@example.com")
        response = await _subscribe(client, "dup@example.com")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "already subscribed" in data["message"].lower()
    # Welcome email sent only once (first subscription)
    assert mock_email.call_count == 1


async def test_subscribe_reactivates_unsubscribed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    import secrets
    from datetime import UTC, datetime

    existing = NewsletterSubscriber(
        email="return@example.com",
        is_active=False,
        unsubscribe_token=secrets.token_hex(32),
        unsubscribed_at=datetime.now(UTC),
    )
    db_session.add(existing)
    await db_session.commit()

    with patch(
        "app.services.newsletter.send_newsletter_welcome_email",
        new_callable=AsyncMock,
    ) as mock_email:
        response = await _subscribe(client, "return@example.com")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "subscribed" in data["message"].lower()
    assert mock_email.call_count == 1

    await db_session.refresh(existing)
    assert existing.is_active is True
    assert existing.unsubscribed_at is None


async def test_subscribe_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/newsletter/subscribe",
        json={"email": "not-an-email"},
    )
    assert response.status_code == 422
    assert response.json()["status"] == "error"


async def test_subscribe_missing_email(client: AsyncClient) -> None:
    response = await client.post("/api/v1/newsletter/subscribe", json={})
    assert response.status_code == 422
    assert response.json()["status"] == "error"


async def test_subscribe_email_delivery_failure_does_not_fail_request(
    client: AsyncClient,
) -> None:
    """A failing welcome email must not surface as a 5xx to the caller."""
    with patch(
        "app.services.newsletter.send_newsletter_welcome_email",
        new_callable=AsyncMock,
        side_effect=Exception("SMTP down"),
    ):
        response = await _subscribe(client, "fail@example.com")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


async def test_subscribe_rate_limit(client: AsyncClient) -> None:
    """The 6th request within one minute must be rejected with 429."""
    with patch(
        "app.services.newsletter.send_newsletter_welcome_email",
        new_callable=AsyncMock,
    ):
        responses = [
            await _subscribe(client, "ratelimit@example.com") for _ in range(6)
        ]

    for resp in responses[:5]:
        assert resp.status_code == 200
    assert responses[5].status_code == 429


# ---------------------------------------------------------------------------
# Unsubscribe tests
# ---------------------------------------------------------------------------


async def test_unsubscribe_success(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    import secrets

    token = secrets.token_hex(32)
    subscriber = NewsletterSubscriber(
        email="unsub@example.com",
        is_active=True,
        unsubscribe_token=token,
    )
    db_session.add(subscriber)
    await db_session.commit()

    response = await client.post(
        "/api/v1/newsletter/unsubscribe",
        json={"token": token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "unsubscribed" in data["message"].lower()

    await db_session.refresh(subscriber)
    assert subscriber.is_active is False
    assert subscriber.unsubscribed_at is not None


async def test_unsubscribe_already_inactive_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    import secrets
    from datetime import UTC, datetime

    token = secrets.token_hex(32)
    subscriber = NewsletterSubscriber(
        email="alreadygone@example.com",
        is_active=False,
        unsubscribe_token=token,
        unsubscribed_at=datetime.now(UTC),
    )
    db_session.add(subscriber)
    await db_session.commit()

    response = await client.post(
        "/api/v1/newsletter/unsubscribe",
        json={"token": token},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"


async def test_unsubscribe_invalid_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/newsletter/unsubscribe",
        json={"token": "nonexistent-token"},
    )
    assert response.status_code == 404
    assert response.json()["status"] == "error"


async def test_unsubscribe_missing_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/newsletter/unsubscribe", json={})
    assert response.status_code == 422
    assert response.json()["status"] == "error"
