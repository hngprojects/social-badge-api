# Unit tests for the sanitize helper
import pytest

from app.core.sanitizer import contains_html, validate_no_html

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
def test_contains_html_detects_all_payloads(payload: str) -> None:
    assert contains_html(payload) is True


@pytest.mark.parametrize("clean", ["Jane", "O'Brien", "José", "van der Berg", ""])
def test_contains_html_passes_clean_values(clean: str) -> None:
    assert contains_html(clean) is False


def test_validate_no_html_raises_on_script() -> None:
    with pytest.raises(ValueError, match="must not contain HTML"):
        validate_no_html("<script>alert(1)</script>", "First name")


def test_validate_no_html_passes_clean_value() -> None:
    result = validate_no_html("Jane", "First name")
    assert result == "Jane"
