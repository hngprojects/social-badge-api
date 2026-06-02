from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_metrics_endpoint_exposes_prometheus_metrics() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.get("/")
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text
    assert 'method="GET"' in response.text
    assert 'route="/"' in response.text
    assert 'status_code="200"' in response.text
    assert "http_request_duration_seconds_bucket" in response.text
    assert "http_requests_in_progress" in response.text
