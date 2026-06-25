from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from string import Template

from app.core.config import settings

EMAIL_TEMPLATES_DIR = Path(__file__).resolve().parent


def render(name: str, **variables: str) -> str:
    """Loads an HTML template by name and substitutes placeholder variables.

    Reads the file from the email templates directory,
    automatically injects default values for `current_year`, `frontend_url`
    (ensuring no trailing slash), and `app_domain` if not explicitly provided,
    and performs a template placeholder substitution.

    Raises:
        ValueError: If a required placeholder substitution fails.
        FileNotFoundError: If the template file `<name>.html` does not exist.
    """
    path = EMAIL_TEMPLATES_DIR / f"{name}.html"
    source = path.read_text(encoding="utf-8")

    variables.setdefault("current_year", str(datetime.now(UTC).year))
    variables.setdefault("frontend_url", settings.FRONTEND_URL)
    variables.setdefault("app_domain", settings.APP_DOMAIN)

    # Ensure frontend_url does not end with a trailing slash to prevent double-slashes
    if "frontend_url" in variables:
        variables["frontend_url"] = variables["frontend_url"].rstrip("/")

    try:
        return Template(source).substitute(variables)
    except KeyError as exc:
        raise ValueError(f"Missing email template variable: {exc.args[0]}") from exc
