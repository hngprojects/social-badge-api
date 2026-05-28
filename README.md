# social-badge-api

Backend API for the Social Badge platform — built with FastAPI, async SQLAlchemy 2.0, Alembic migrations, and `uv` for dependency management.

---

## Stack

| Layer                | Choice                                            |
| -------------------- | ------------------------------------------------- |
| Web framework        | FastAPI (`fastapi[all]`)                          |
| Server               | Uvicorn                                           |
| ORM                  | SQLAlchemy 2.0 (async)                            |
| DB driver            | `asyncpg`                                         |
| Migrations           | Alembic (async-aware)                             |
| Config               | `pydantic-settings` (reads `.env`)                |
| Package manager      | `uv`                                              |
| Cache / Rate Limit   | Redis                                             |
| Linting / Formatting | Ruff                                              |
| Type checking        | mypy (strict)                                     |
| Tests                | `pytest` + `pytest-asyncio` + `httpx.AsyncClient` |
| CI                   | GitHub Actions                                    |
| Python               | 3.13+                                             |

---

## Project structure

```
social-badge-api/
├── app/
│   ├── main.py                # FastAPI() instance, middleware, lifespan
│   ├── dependencies.py        # Shared FastAPI dependencies (Annotated types)
│   ├── core/
│   │   ├── config.py          # Settings (env-driven via pydantic-settings)
│   │   ├── exceptions/        # Global exception handlers + custom errors
│   │   ├── middleware/        # ContentSizeLimitMiddleware
│   │   ├── ip.py              # IP address resolution
│   │   ├── pillow.py          # Pillow decompression-bomb config
│   │   ├── rate_limit.py      # slowapi configuration
│   │   ├── sanitizer.py       # Input sanitization helpers
│   │   ├── security.py        # Password hashing + verification
│   │   ├── slug.py            # Share-slug generation
│   │   └── token.py           # JWT creation + decoding
│   ├── db/
│   │   ├── session.py         # Async engine + session factory
│   │   ├── redis.py           # Redis connection pool
│   │   └── seed/              # Database seed data
│   ├── models/                # SQLAlchemy ORM models
│   │   ├── base.py            # DeclarativeBase
│   │   ├── auth.py
│   │   ├── badges.py
│   │   ├── newsletter.py
│   │   ├── roles.py
│   │   ├── templates.py
│   │   └── users.py
│   ├── routers/
│   │   └── v1/
│   │       ├── __init__.py    # Aggregates all v1 endpoint routers
│   │       ├── admin.py
│   │       ├── auth.py
│   │       ├── badges.py
│   │       ├── contact.py
│   │       ├── health.py      # DB-backed health check endpoint
│   │       ├── newsletter.py
│   │       ├── platform_templates.py
│   │       └── profile.py
│   ├── schemas/               # Pydantic request/response models
│   └── services/              # Business logic layer
├── alembic/
│   ├── env.py                 # Wired to app.models.Base.metadata + settings
│   ├── script.py.mako
│   └── versions/              # Migration files
├── tests/                     # pytest test suite (mirrors app/ structure)
│   └── conftest.py            # Fixtures: AsyncClient, db_session, test_user
├── scripts/                   # Utility scripts
├── .github/
│   ├── workflows/
│   │   ├── CI.yml
│   │   ├── CD.yml
│   │   └── vulnerability_scanner.yml
│   └── PULL_REQUEST_TEMPLATE.md
├── .env.example
├── .pre-commit-config.yaml    # Ruff hooks for local dev
├── alembic.ini
├── pyproject.toml
└── uv.lock
```

### Why this layout

- **`app/` package** — keeps imports absolute and clean (`from app.core.config import settings`).
- **`routers/v1/`** — versioning is free; add `v2/` later without touching `v1/`.
- **`models` / `schemas` / `services` split** — DB shape, API shape, and business logic stay decoupled.
- **`dependencies.py`** — centralized dependency management using `Annotated` for cleaner endpoint signatures.

---

## Getting started

### 1. Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **PostgreSQL**: A running instance (local, Docker, or remote).
- **Redis**: A running instance for rate limiting.

### 2a. Install

```bash
uv sync --dev
```

This installs both runtime and dev dependencies (`pytest`, `ruff`, `mypy`, etc.).

### 2b. Set up pre-commit hooks

```bash
uv run pre-commit install
```

This installs git hooks that run `ruff check --fix` and `ruff format` on every commit.

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` and set the required variables. The database driver **must** be `postgresql+asyncpg`:

```env
ENVIRONMENT=local
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/social_badge
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your_super_secret_key_here
```

### 4. Create the database

```bash
createdb social_badge
# or, with psql:
psql -U postgres -c "CREATE DATABASE social_badge;"
```

### 5. Run migrations

Apply all pending migrations:

```bash
uv run alembic upgrade head
```

To generate a new migration after editing a model:

```bash
uv run alembic revision --autogenerate -m "describe the change"
# Review the generated file in alembic/versions/ before applying.
uv run alembic upgrade head
```

### 6. Start the server

```bash
uvicorn app.main:app --access-log False --log-config logging.yaml
```

Open:

- App root → http://127.0.0.1:8000
- Health check → http://127.0.0.1:8000/api/v1/health
- Swagger UI → http://127.0.0.1:8000/docs

---

## Code quality

### Linting and formatting

```bash
# Check for lint errors
uv run ruff check .

# Apply formatting
uv run ruff format .
```

### Type checking

```bash
uv run mypy .
```

### Running tests

```bash
uv run pytest
```

`pytest-asyncio` is set to `auto` mode in `pyproject.toml`, so async tests don't need a decorator. Tests use `httpx.AsyncClient` with `ASGITransport` — no live server required.

**Isolation**: The test suite automatically truncates all database tables and resets Redis state after every single test, ensuring no data leakage between test runs.

---

## CI

GitHub Actions runs jobs on every push and PR to `dev`, `staging`, and `main`:

| Job      | What it checks                            |
| -------- | ----------------------------------------- |
| **Lint** | `flake8` (line length 120, exits zero)    |
| **Test** | `pytest` (short tracebacks, quiet output) |

The workflow is defined in `.github/workflows/CI.yml`. A CD pipeline (`.github/workflows/CD.yml`) deploys to staging and production on pushes to `staging` and `main` respectively.

---

## Migrations workflow

Migrations are the single source of truth for your schema. Treat them as code: review, commit, and never edit applied ones.

### Typical cycle

```bash
# 1. Edit a model in app/models/
# 2. Generate a migration
uv run alembic revision --autogenerate -m "add user table"

# 3. Open alembic/versions/<hash>_add_user_table.py and REVIEW it.
#    Autogenerate is not perfect — check column types, indexes, defaults.

# 4. Apply
uv run alembic upgrade head
```

### Useful commands

| Command                                    | What it does                            |
| ------------------------------------------ | --------------------------------------- |
| `alembic revision --autogenerate -m "msg"` | Diff models vs DB and write a migration |
| `alembic revision -m "msg"`                | Empty migration (write SQL by hand)     |
| `alembic upgrade head`                     | Apply all pending migrations            |
| `alembic upgrade +1` / `downgrade -1`      | Step forward/back one revision          |
| `alembic current`                          | Show what's applied                     |
| `alembic history`                          | Full migration chain                    |
| `alembic downgrade base`                   | Wipe back to empty (dev only)           |

### Rules of thumb

- **Always review** the autogenerated file before applying. Alembic misses enum changes, server-side defaults, and some index renames.
- **Never edit a migration after it's been applied** to a shared environment. Write a new one instead.
- **Fill in `downgrade()`**, even if you never plan to run it. It's the cheapest safety net you'll get.
- **Run migrations during deploy, not at app startup**. Run `alembic upgrade head` in CI/CD before booting the new app.
- **Commit `alembic/versions/`** to git so the migration chain stays consistent across machines.

---

## Adding new code

### A new endpoint

1. Create the router module: `app/routers/v1/users.py`
2. Define an `APIRouter()` and your routes.
3. Register it in `app/routers/v1/__init__.py`:

   ```python
   from app.routers.v1 import health, users

   api_router.include_router(users.router, prefix="/users", tags=["users"])
   ```

### A new model

1. Create `app/models/user.py`
2. Subclass `Base` from `app.models.base`.
3. Re-export from `app/models/__init__.py` so Alembic discovers it.
4. Generate + apply a migration.

### A new Pydantic schema

Put request/response models in `app/schemas/`. Use `SuccessResponse` and `ErrorResponse` from `app/schemas/response.py` for consistent API envelopes.

---

## Conventions

- **Absolute imports only** (`from app.foo import bar`), never relative.
- **Type hints everywhere.**
- **Endpoints return Pydantic models**, using standardized response envelopes.
- **Use `Annotated` dependencies** (see `app/dependencies.py`).
- **`async def` for I/O bound tasks**.

---

## Production notes

- Start the server with `uvicorn app.main:app --access-log False --log-config logging.yaml`.
- Run `alembic upgrade head` as a deployment step.
- Ensure `SECRET_KEY` and other sensitive variables are managed via environment secrets.
- Set `echo=False` on the engine (already the default) and configure pool size to match your worker count.
- Keep `.env` out of git (already in `.gitignore`); use your platform's secret store in production.
