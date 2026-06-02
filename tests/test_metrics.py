from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

FAKE_TOKEN = "test-metrics-secret"


async def test_metrics_endpoint_exposes_prometheus_metrics() -> None:
    with patch("app.main.settings") as mock_settings:
        mock_settings.METRICS_TOKEN = FAKE_TOKEN

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            await client.get("/")
            response = await client.get(
                "/metrics", headers={"Authorization": f"Bearer {FAKE_TOKEN}"}
            )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text
    assert 'method="GET"' in response.text
    assert 'route="/"' in response.text
    assert 'status_code="200"' in response.text
    assert "http_request_duration_seconds_bucket" in response.text
    assert "http_requests_in_progress" in response.text


async def test_metrics_endpoint_rejects_missing_token() -> None:
    with patch("app.main.settings") as mock_settings:
        mock_settings.METRICS_TOKEN = FAKE_TOKEN

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics")

    assert response.status_code == 401


async def test_metrics_endpoint_rejects_wrong_token() -> None:
    with patch("app.main.settings") as mock_settings:
        mock_settings.METRICS_TOKEN = FAKE_TOKEN

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/metrics", headers={"Authorization": "Bearer wrong-token"}
            )

    assert response.status_code == 401


@pytest.mark.parametrize("auth_header", [None, "Bearer anything"])
async def test_metrics_endpoint_open_when_token_unset(auth_header: str | None) -> None:
    with patch("app.main.settings") as mock_settings:
        mock_settings.METRICS_TOKEN = ""

        headers = {"Authorization": auth_header} if auth_header else {}
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/metrics", headers=headers)

    assert response.status_code == 200
