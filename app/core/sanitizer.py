import re

_HTML_TAG_PATTERN = re.compile(r"<.*?>", re.IGNORECASE)
_EVENT_HANDLER_PATTERN = re.compile(r"\b(on\w+)\s*=", re.IGNORECASE)
_DANGEROUS_PROTOCOLS = re.compile(r"(javascript|vbscript|data)\s*:", re.IGNORECASE)


def contains_html(value: str) -> bool:
    return bool(
        _HTML_TAG_PATTERN.search(value)
        or _EVENT_HANDLER_PATTERN.search(value)
        or _DANGEROUS_PROTOCOLS.search(value)
    )


def validate_no_html(value: str, field_name: str = "Field") -> str:
    if contains_html(value):
        raise ValueError(f"{field_name} must not contain HTML tags or scripts")

    return value
