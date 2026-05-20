from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from string import Template

from app.core.config import settings

EMAIL_TEMPLATES_DIR = Path(__file__).resolve().parent


def render(name: str, **variables: str) -> str:
    """Load `<name>.html` and substitute `$placeholders`.

    Common variables (`current_year`, `frontend_url`) are injected
    automatically but can be overridden.
    """
    path = EMAIL_TEMPLATES_DIR / f"{name}.html"
    source = path.read_text(encoding="utf-8")

    variables.setdefault("current_year", str(datetime.now(UTC).year))
    variables.setdefault("frontend_url", settings.FRONTEND_URL)
    variables.setdefault("app_domain", settings.APP_DOMAIN)

    return Template(source).safe_substitute(variables)
