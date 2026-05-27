from httpx import AsyncClient

from app.core.config import settings


async def test_body_over_5mb_returns_413(client: AsyncClient) -> None:
    huge_password = "A" * (settings.MAX_CONTENT_BODY_SIZE + 1)
    body = {"email": "attacker@example.com", "password": huge_password}
    response = await client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 413
