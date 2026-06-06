import re
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.exceptions import EmailDeliveryError
from app.schemas.contact import ContactRequest, ContactSubjectOption, ContactTopic
from app.services.contact import get_contact_subjects


@pytest.fixture
def valid_contact_payload() -> dict[str, str]:
    return {
        "first_name": "Alex",
        "last_name": "Rivera",
        "email": "alex@yourcompany.com",
        "subject": "general",
        "message": "I have a question about setting up my first badge template.",
    }


class TestContactRequestSchema:
    def test_valid_payload(self, valid_contact_payload: dict[str, str]) -> None:
        # Use type: ignore for dict unpacking with mixed types if needed,
        # or explicitly map types.
        payload = {**valid_contact_payload, "subject": ContactTopic.GENERAL}
        req = ContactRequest(**payload)  # type: ignore[arg-type]
        assert req.first_name == "Alex"
        assert req.last_name == "Rivera"
        assert req.email == "alex@yourcompany.com"
        assert req.subject == ContactTopic.GENERAL
        assert "badge template" in req.message

    def test_strips_whitespace(self) -> None:
        req = ContactRequest(
            first_name="  Alex  ",
            last_name="  Rivera  ",
            email="  ALEX@Example.COM  ",
            subject=ContactTopic.GENERAL,
            message="  This is a long enough test message.  ",
        )
        assert req.first_name == "Alex"
        assert req.last_name == "Rivera"
        assert req.email == "alex@example.com"
        assert req.message == "This is a long enough test message."

    def test_last_name_optional(self) -> None:
        req = ContactRequest(
            first_name="Alex",
            last_name=None,
            email="alex@example.com",
            subject=ContactTopic.FEEDBACK,
            message="This is a long enough test message.",
        )
        assert req.last_name is None

    def test_blank_last_name_becomes_none(self) -> None:
        req = ContactRequest(
            first_name="Alex",
            last_name="   ",
            email="alex@example.com",
            subject=ContactTopic.FEEDBACK,
            message="This is a long enough test message.",
        )
        assert req.last_name is None

    def test_rejects_empty_first_name(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ContactRequest(
                first_name="   ",
                last_name=None,
                email="alex@example.com",
                subject=ContactTopic.GENERAL,
                message="This is a long enough test message.",
            )
        assert "First name cannot be empty" in str(exc_info.value)

    def test_rejects_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            ContactRequest(
                first_name="Alex",
                last_name=None,
                email="not-an-email",
                subject=ContactTopic.GENERAL,
                message="This is a long enough test message.",
            )

    def test_rejects_invalid_subject(self) -> None:
        with pytest.raises(ValidationError):
            ContactRequest(
                first_name="Alex",
                last_name=None,
                email="alex@example.com",
                subject="invalid_topic",  # type: ignore[arg-type]
                message="This is a long enough test message.",
            )

    def test_rejects_short_message(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ContactRequest(
                first_name="Alex",
                last_name=None,
                email="alex@example.com",
                subject=ContactTopic.GENERAL,
                message="Short",
            )
        assert "at least 10 characters" in str(exc_info.value)

    def test_rejects_long_message(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ContactRequest(
                first_name="Alex",
                last_name=None,
                email="alex@example.com",
                subject=ContactTopic.GENERAL,
                message="x" * 501,
            )
        assert "500 characters" in str(exc_info.value)

    @pytest.mark.parametrize(
        "topic",
        [
            ContactTopic.GENERAL,
            ContactTopic.PARTNERSHIP,
            ContactTopic.BUG_REPORT,
            ContactTopic.FEEDBACK,
            ContactTopic.BILLING,
            ContactTopic.OTHER,
        ],
    )
    def test_all_topics_accepted(self, topic: ContactTopic) -> None:
        req = ContactRequest(
            first_name="Alex",
            last_name=None,
            email="alex@example.com",
            subject=topic,
            message="This is a long enough test message.",
        )
        assert req.subject == topic


@patch(
    "app.services.contact.send_contact_confirmation",
    new_callable=AsyncMock,
)
@patch(
    "app.services.contact.send_contact_notification",
    new_callable=AsyncMock,
)
async def test_contact_endpoint_success(
    mock_notification: AsyncMock,
    mock_confirmation: AsyncMock,
    client: AsyncClient,
    valid_contact_payload: dict[str, str],
) -> None:
    response = await client.post("/api/v1/contact", json=valid_contact_payload)
    assert response.status_code == 201

    data = response.json()
    assert data["status"] == "success"
    assert "Thanks for reaching out" in data["message"]
    assert data["data"]["email"] == "alex@yourcompany.com"
    assert data["data"]["reference_id"].startswith("CONTACT-")

    mock_notification.assert_called_once()
    mock_confirmation.assert_called_once()


@patch(
    "app.services.contact.send_contact_confirmation",
    new_callable=AsyncMock,
)
@patch(
    "app.services.contact.send_contact_notification",
    new_callable=AsyncMock,
)
async def test_contact_endpoint_without_last_name(
    mock_notification: AsyncMock,
    mock_confirmation: AsyncMock,
    client: AsyncClient,
) -> None:
    payload = {
        "first_name": "Alex",
        "email": "alex@example.com",
        "subject": "feedback",
        "message": "This is a valid contact message for testing.",
    }
    response = await client.post("/api/v1/contact", json=payload)
    assert response.status_code == 201

    # Verify last_name was passed as None to the notification
    call_kwargs = mock_notification.call_args.kwargs
    assert call_kwargs["last_name"] is None


async def test_contact_endpoint_validation_error(client: AsyncClient) -> None:
    payload = {
        "first_name": "",
        "email": "not-an-email",
        "subject": "invalid",
        "message": "short",
    }
    response = await client.post("/api/v1/contact", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert data["status"] == "error"


async def test_contact_endpoint_missing_required_fields(client: AsyncClient) -> None:
    response = await client.post("/api/v1/contact", json={})
    assert response.status_code == 422


@patch(
    "app.services.contact.send_contact_notification",
    new_callable=AsyncMock,
)
async def test_contact_endpoint_email_delivery_failure(
    mock_notification: AsyncMock,
    client: AsyncClient,
    valid_contact_payload: dict[str, str],
) -> None:
    mock_notification.side_effect = EmailDeliveryError("Resend API down")

    response = await client.post("/api/v1/contact", json=valid_contact_payload)
    assert response.status_code == 502

    data = response.json()
    assert data["status"] == "error"
    assert "email service error" in data["message"]


@patch(
    "app.services.contact.send_contact_confirmation",
    new_callable=AsyncMock,
)
@patch(
    "app.services.contact.send_contact_notification",
    new_callable=AsyncMock,
)
async def test_contact_endpoint_confirmation_failure_still_succeeds(
    mock_notification: AsyncMock,
    mock_confirmation: AsyncMock,
    client: AsyncClient,
    valid_contact_payload: dict[str, str],
) -> None:
    """If the confirmation email fails, the request should still succeed."""
    mock_confirmation.side_effect = RuntimeError("Unexpected error")

    response = await client.post("/api/v1/contact", json=valid_contact_payload)
    assert response.status_code == 201

    data = response.json()
    assert data["status"] == "success"
    assert data["data"]["reference_id"].startswith("CONTACT-")


@patch(
    "app.services.contact.send_contact_confirmation",
    new_callable=AsyncMock,
)
@patch(
    "app.services.contact.send_contact_notification",
    new_callable=AsyncMock,
)
async def test_contact_endpoint_rate_limit(
    mock_notification: AsyncMock,
    mock_confirmation: AsyncMock,
    client: AsyncClient,
    valid_contact_payload: dict[str, str],
) -> None:
    for _ in range(5):
        await client.post("/api/v1/contact", json=valid_contact_payload)

    # 6th request should be rate-limited
    response = await client.post("/api/v1/contact", json=valid_contact_payload)
    assert response.status_code == 429

    data = response.json()
    assert data["status"] == "error"
    assert data["message"] == "Rate limit exceeded"


@patch(
    "app.services.contact.send_contact_confirmation",
    new_callable=AsyncMock,
)
@patch(
    "app.services.contact.send_contact_notification",
    new_callable=AsyncMock,
)
async def test_submit_contact_form_returns_reference_id(
    mock_notification: AsyncMock,
    mock_confirmation: AsyncMock,
) -> None:
    from app.services.contact import submit_contact_form

    payload = ContactRequest(
        first_name="Alex",
        last_name="Rivera",
        email="alex@example.com",
        subject=ContactTopic.GENERAL,
        message="This is a valid contact message for testing.",
    )
    reference_id = await submit_contact_form(payload)

    assert reference_id.startswith("CONTACT-")
    # Validate format: CONTACT-<4-digit year>-<6 alphanumeric chars>
    assert re.match(r"^CONTACT-\d{4}-[A-Z0-9]{6}$", reference_id)

    mock_notification.assert_called_once()
    notification_kwargs = mock_notification.call_args.kwargs
    assert notification_kwargs["reference_id"] == reference_id
    assert notification_kwargs["first_name"] == "Alex"
    assert notification_kwargs["last_name"] == "Rivera"
    assert notification_kwargs["subject"] == "General Question"

    mock_confirmation.assert_called_once()
    confirmation_kwargs = mock_confirmation.call_args.kwargs
    assert confirmation_kwargs["reference_id"] == reference_id
    assert confirmation_kwargs["first_name"] == "Alex"


@patch(
    "app.services.contact.send_contact_confirmation",
    new_callable=AsyncMock,
)
@patch(
    "app.services.contact.send_contact_notification",
    new_callable=AsyncMock,
)
async def test_submit_contact_form_notification_failure_propagates(
    mock_notification: AsyncMock,
    mock_confirmation: AsyncMock,
) -> None:
    """EmailDeliveryError from the notification should propagate to caller."""
    from app.services.contact import submit_contact_form

    mock_notification.side_effect = EmailDeliveryError("Resend failed")

    payload = ContactRequest(
        first_name="Alex",
        last_name=None,
        email="alex@example.com",
        subject=ContactTopic.BUG_REPORT,
        message="This is a valid contact message for testing.",
    )

    with pytest.raises(EmailDeliveryError):
        await submit_contact_form(payload)

    # Confirmation should not have been attempted
    mock_confirmation.assert_not_called()


# ---------------------------------------------------------------------------
# Email HTML builder tests
# ---------------------------------------------------------------------------


def test_notification_html_escapes_user_input() -> None:
    from app.services.email import _build_notification_html

    result = _build_notification_html(
        reference_id="CONTACT-2026-TEST01",
        first_name='<script>alert("xss")</script>',
        last_name=None,
        email="test@example.com",
        subject="General Question",
        message="<img src=x onerror=alert(1)>",
    )

    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "<img src=" not in result
    assert "&lt;img" in result


def test_confirmation_html_escapes_first_name() -> None:
    from app.services.email import _build_confirmation_html

    result = _build_confirmation_html(
        first_name='<script>alert("xss")</script>',
        reference_id="CONTACT-2026-TEST01",
    )

    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_notification_html_includes_all_fields() -> None:
    from app.services.email import _build_notification_html

    result = _build_notification_html(
        reference_id="CONTACT-2026-ABC123",
        first_name="Alex",
        last_name="Rivera",
        email="alex@example.com",
        subject="Bug Report",
        message="Something is broken.",
    )

    assert "CONTACT-2026-ABC123" in result
    assert "Alex Rivera" in result
    assert "alex@example.com" in result
    assert "Bug Report" in result
    assert "Something is broken." in result


_XSS_PAYLOADS = [
    "<script>alert('XSS')</script>",
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "javascript:alert(1)",
    "<a href='javascript:void(0)' onclick=alert(1)>click</a>",
    "<SCRIPT>alert('xss')</SCRIPT>",
    "data:text/html,<script>alert(1)</script>",
    "<body onload=alert(1)>",
]


@pytest.mark.parametrize("payload", _XSS_PAYLOADS)
async def test_contact_rejects_xss_in_first_name(
    client: AsyncClient,
    payload: str,
) -> None:
    body = {
        "first_name": payload,
        "last_name": "Doe",
        "email": "xsscontact@example.com",
        "subject": "general",
        "message": "This is a clean message that is long enough.",
    }
    response = await client.post("/api/v1/contact", json=body)
    assert response.status_code == 422
    assert response.json()["status"] == "error"


@pytest.mark.parametrize("payload", _XSS_PAYLOADS)
async def test_contact_rejects_xss_in_message(
    client: AsyncClient,
    payload: str,
) -> None:
    body = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "xsscontact2@example.com",
        "subject": "general",
        "message": payload,
    }
    response = await client.post("/api/v1/contact", json=body)
    assert response.status_code == 422
    assert response.json()["status"] == "error"


@pytest.mark.parametrize("payload", _XSS_PAYLOADS)
async def test_contact_rejects_xss_in_last_name(
    client: AsyncClient,
    payload: str,
) -> None:
    body = {
        "first_name": "Jane",
        "last_name": payload,
        "email": "xsscontact3@example.com",
        "subject": "general",
        "message": "This is a clean message that is long enough.",
    }
    response = await client.post("/api/v1/contact", json=body)
    assert response.status_code == 422
    assert response.json()["status"] == "error"


# ---------------------------------------------------------------------------
# GET /contact/subjects tests
# ---------------------------------------------------------------------------


async def test_get_contact_subjects_returns_all_options(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/contact/subjects")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert data["message"] == "Contact subject options retrieved successfully"

    subjects = data["data"]
    assert isinstance(subjects, list)
    assert len(subjects) == len(ContactTopic)

    # Each entry must have value and label keys
    for entry in subjects:
        assert "value" in entry
        assert "label" in entry

    # All enum values must be present
    returned_values = {s["value"] for s in subjects}
    expected_values = {topic.value for topic in ContactTopic}
    assert returned_values == expected_values


async def test_get_contact_subjects_values_match_enum(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/contact/subjects")
    subjects = response.json()["data"]

    valid_values = {topic.value for topic in ContactTopic}
    for entry in subjects:
        assert entry["value"] in valid_values


async def test_get_contact_subjects_labels_are_nonempty(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/contact/subjects")
    subjects = response.json()["data"]

    for entry in subjects:
        assert isinstance(entry["label"], str)
        assert len(entry["label"].strip()) > 0


async def test_get_contact_subjects_order_matches_enum(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/contact/subjects")
    subjects = response.json()["data"]

    expected_order = [topic.value for topic in ContactTopic]
    actual_order = [s["value"] for s in subjects]
    assert actual_order == expected_order


def test_get_contact_subjects_service_returns_subject_options() -> None:
    subjects = get_contact_subjects()
    assert isinstance(subjects, list)
    assert len(subjects) == len(ContactTopic)
    assert all(isinstance(s, ContactSubjectOption) for s in subjects)


def test_get_contact_subjects_service_is_idempotent() -> None:
    """Calling twice returns the same cached list."""
    first = get_contact_subjects()
    second = get_contact_subjects()
    assert first is second

