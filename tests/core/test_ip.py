"""Tests for IP masking helpers."""

from unittest.mock import MagicMock

from app.core.ip import get_client_ip, mask_ip

# ---------------------------------------------------------------------------
# get_client_ip helpers
# ---------------------------------------------------------------------------


def _make_request(
    forwarded: str | None = None,
    real_ip: str | None = None,
    client_host: str | None = "127.0.0.1",
) -> MagicMock:
    req = MagicMock()
    headers: dict[str, str] = {}
    if forwarded is not None:
        headers["X-Forwarded-For"] = forwarded
    if real_ip is not None:
        headers["X-Real-IP"] = real_ip
    req.headers = headers
    if client_host is not None:
        req.client = MagicMock()
        req.client.host = client_host
    else:
        req.client = None
    return req


# ---------------------------------------------------------------------------
# get_client_ip tests
# ---------------------------------------------------------------------------


def test_get_client_ip_uses_x_forwarded_for() -> None:
    assert get_client_ip(_make_request(forwarded="10.0.0.1")) == "10.0.0.1"


def test_get_client_ip_x_forwarded_for_returns_first_ip() -> None:
    req = _make_request(forwarded="10.0.0.1, 10.0.0.2, 10.0.0.3")
    assert get_client_ip(req) == "10.0.0.1"


def test_get_client_ip_x_forwarded_for_strips_whitespace() -> None:
    req = _make_request(forwarded="  1.2.3.4  , 5.6.7.8")
    assert get_client_ip(req) == "1.2.3.4"


def test_get_client_ip_falls_back_to_x_real_ip() -> None:
    req = _make_request(real_ip="192.168.1.10")
    assert get_client_ip(req) == "192.168.1.10"


def test_get_client_ip_x_real_ip_strips_whitespace() -> None:
    req = _make_request(real_ip="  192.168.1.10  ")
    assert get_client_ip(req) == "192.168.1.10"


def test_get_client_ip_falls_back_to_client_host() -> None:
    req = _make_request(client_host="203.0.113.5")
    assert get_client_ip(req) == "203.0.113.5"


def test_get_client_ip_returns_none_when_client_is_none() -> None:
    req = _make_request(client_host=None)
    assert get_client_ip(req) is None


def test_get_client_ip_prefers_x_forwarded_for_over_x_real_ip() -> None:
    req = _make_request(forwarded="10.0.0.1", real_ip="192.168.1.10")
    assert get_client_ip(req) == "10.0.0.1"


def test_get_client_ip_prefers_x_forwarded_for_over_client_host() -> None:
    req = _make_request(forwarded="10.0.0.1", client_host="127.0.0.1")
    assert get_client_ip(req) == "10.0.0.1"


# ---------------------------------------------------------------------------
# mask_ip tests
# ---------------------------------------------------------------------------


def test_mask_ipv4_last_octet() -> None:
    assert mask_ip("41.184.22.5") == "41.184.22.x"


def test_mask_ipv4_preserves_prefix() -> None:
    result = mask_ip("192.168.1.100")
    assert result == "192.168.1.x"


def test_mask_ipv6_last_group() -> None:
    assert mask_ip("2001:db8::1") == "2001:db8::x"


def test_mask_none_returns_none() -> None:
    assert mask_ip(None) is None


def test_mask_preserves_ipv4_structure() -> None:
    result = mask_ip("10.0.0.1")
    parts = result.split(".")
    assert len(parts) == 4
    assert parts[-1] == "x"
