import re
from re import Pattern
from typing import Any

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


class DataSanitizer:
    """Comprehensive data sanitizer for removing/masking sensitive information
    from logs, exceptions, and other outputs.
    """

    SENSITIVE_HEADERS: frozenset[str] = frozenset(
        {
            "authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "x-auth-token",
            "x-csrf-token",
            "x-forwarded-for",
            "x-real-ip",
            "proxy-authorization",
        }
    )

    def __init__(self) -> None:
        # Tightened patterns to avoid masking 'status_code', 'api_version', etc.
        self.sensitive_patterns: list[Pattern[str]] = [
            re.compile(r"^password$", re.IGNORECASE),
            re.compile(r"passwd", re.IGNORECASE),
            re.compile(r"secret", re.IGNORECASE),
            re.compile(r"access_token", re.IGNORECASE),
            re.compile(r"refresh_token", re.IGNORECASE),
            re.compile(r"api[-_]?key", re.IGNORECASE),
            re.compile(r"auth[-_]?token", re.IGNORECASE),
            re.compile(r"session[-_]?id", re.IGNORECASE),
            re.compile(r"csrf[-_]?token", re.IGNORECASE),
        ]

        self.email_pattern = re.compile(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        )
        self.query_params_pattern = re.compile(
            r"(?:^|\s)([a-zA-Z_][a-zA-Z0-9_]*=[^&\s]+(?:&[a-zA-Z_][a-zA-Z0-9_]*=[^&\s]+)*)(?:\s|$)"
        )

    def sanitize_headers(self, headers: dict) -> dict[str, str]:
        """Redact values of sensitive HTTP headers."""
        return {
            name: value
            for name, value in headers.items()
            if name.lower() not in self.SENSITIVE_HEADERS
        }

    def sanitize_query(self, query_string: str) -> str:
        """Redact values of sensitive query-string parameters."""
        if not query_string:
            return ""
        try:
            params = {}
            for param_pair in query_string.split("&"):
                if "=" in param_pair:
                    key, value = param_pair.split("=", 1)
                    params[key] = value
                else:
                    params[param_pair] = ""

            sanitized_params = {}
            for key, value in params.items():
                if self._is_sensitive_field(key):
                    sanitized_params[key] = "[REDACTED]"
                else:
                    sanitized_params[key] = value

            return "&".join([f"{k}={v}" for k, v in sanitized_params.items()])
        except Exception:
            return "***SANITIZED_PARAMS***"

    def sanitize_for_logging(self, data: Any) -> Any:
        return self._sanitize_value(data)

    def sanitize_sql_for_logging(self, sql: str, params: Any) -> tuple[str, Any]:
        return self._sanitize_sql_params(sql, params)

    def sanitize_exception_for_logging(self, exception: Any) -> Any:
        try:
            try:
                # If it's an exception, try to sanitize its args
                sanitized_args = self._sanitize_exception_args(exception.args)
                if sanitized_args == ():
                    raise ValueError("Empty args")  # trigger fallback
            except Exception:
                sanitized_args = self._sanitize_exception_args(exception)
            return sanitized_args
        except Exception:
            exc_type = type(exception).__name__
            return Exception(f"***SANITIZED*** {exc_type}")

    def _is_sensitive_field(self, field_name: str) -> bool:
        return any(pattern.search(field_name) for pattern in self.sensitive_patterns)

    def _mask_email(self, email: str) -> str:
        if "@" in email:
            local, domain = email.split("@", 1)
            if len(local) <= 2:
                masked_local = "*" * len(local)
            else:
                masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
            return f"{masked_local}@{domain}"
        return "***@***.***"

    def _sanitize_string(self, text: str, max_length: int = 1000) -> str:
        if not isinstance(text, str):
            text = str(text)

        if len(text) > max_length:
            text = text[:max_length] + "..."

        text = self.email_pattern.sub(lambda m: self._mask_email(m.group()), text)

        # Mask loose query-like patterns anywhere in text (key=value)
        text = re.sub(
            r"([?&]?(?:\w+))=([^&\s]+)",
            lambda m: (
                f"{m.group(1)}=[REDACTED]"
                if self._is_sensitive_field(m.group(1).lstrip("?&"))
                else m.group(0)
            ),
            text,
        )

        return text

    def _sanitize_dict(
        self, data: dict[str, Any], max_depth: int = 5
    ) -> dict[str, Any]:
        if max_depth <= 0:
            return {"<max_depth_reached>": "..."}

        sanitized = {}
        for key, value in data.items():
            if self._is_sensitive_field(key):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = self._sanitize_value(value, max_depth - 1)

        return sanitized

    def _sanitize_list(self, data: list[Any], max_depth: int = 5) -> list[Any]:
        if max_depth <= 0:
            return ["<max_depth_reached>"]
        return [self._sanitize_value(item, max_depth - 1) for item in data[:10]]

    def _sanitize_value(self, value: Any, max_depth: int = 5) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return self._sanitize_dict(value, max_depth)
        elif isinstance(value, (list, tuple)):
            return self._sanitize_list(list(value), max_depth)
        elif isinstance(value, (int, float, bool)):
            return value
        else:
            return self._sanitize_string(str(value))

    def _sanitize_sql_params(self, sql: str, params: Any) -> tuple[str, Any]:
        sanitized_sql = sql
        has_sensitive_fields = any(
            pattern.search(sql) for pattern in self.sensitive_patterns
        )

        if isinstance(params, (list, tuple)):
            sanitized_params = []
            for param in params:
                should_mask = False
                if isinstance(param, str):
                    if "$2b$" in param or "$argon2" in param or len(param) > 36:
                        should_mask = True
                    elif has_sensitive_fields and len(str(param)) > 5:
                        should_mask = True

                if should_mask:
                    sanitized_params.append("[REDACTED]")
                else:
                    sanitized_params.append(self._sanitize_value(param))
            return sanitized_sql, sanitized_params
        elif isinstance(params, dict):
            return sanitized_sql, self._sanitize_dict(params)
        else:
            return sanitized_sql, self._sanitize_value(params)

    def _sanitize_exception_args(
        self, exc_args: str | tuple | dict[str, Any] | Exception
    ) -> tuple:
        sanitized_args = []
        if isinstance(exc_args, tuple):
            for arg in exc_args:
                if isinstance(arg, str):
                    if "[parameters:" in arg:
                        arg = re.sub(
                            r"\[parameters: \([^)]+\)\]",
                            "[parameters: ***SANITIZED***]",
                            arg,
                        )
                    sanitized_args.append(self._sanitize_string(arg))
                else:
                    sanitized_args.append(self._sanitize_value(arg))
        elif isinstance(exc_args, dict):
            sanitized_args.append(
                [
                    f"{key}={value}"
                    for key, value in self._sanitize_dict(exc_args).items()
                ]
            )
        else:
            sanitized_args.append(self._sanitize_value(str(exc_args)))
        return tuple(sanitized_args)


data_sanitizer = DataSanitizer()
