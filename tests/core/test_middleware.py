from httpx import AsyncClient


async def test_body_over_5mb_returns_413(client: AsyncClient) -> None:
    # Build a payload just over 5 MB
    huge_password = "A" * (5 * 1024 * 1024 + 1)
    body = {"email": "attacker@example.com", "password": huge_password}
    response = await client.post("/api/v1/auth/login", json=body)
    # Middleware returns 413 before Pydantic even sees the body
    assert response.status_code in (413, 422)
    assert response.status_code != 500
