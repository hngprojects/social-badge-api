"""Tests for IP masking helpers."""

from app.core.ip import mask_ip


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
