Setup — Badges Service

This document explains how to set up and run the Badges Service locally for development, testing, and simple deployments.

Prerequisites

- Python 3.13
- Git
- Redis (for queueing with RQ) — optional for synchronous local testing
- `uv` development helper (used by this repo) or a Python virtualenv

Environment variables

- `DATABASE_URL` (required)
  - Example: `sqlite:///./dev_badges.db` or `postgresql+psycopg2://user:pass@localhost/dbname`
- `REDIS_URL` (required for RQ queueing)
  - Example: `redis://localhost:6379/0`
- `BADGE_DIR` (optional)
  - Directory where generated badge files are saved. Defaults to `badges`.

Install dependencies

From the repository root:

```bash
# Using the repo's helper tool (recommended for this workspace)
uv sync

# Or create a venv and install requirements manually
python -m venv .venv
source .venv/bin/activate
pip install -r services/badges/requirements.txt
pip install -e .
```

Database setup

- For quick local development you can use SQLite:

```bash
export DATABASE_URL=sqlite:///./dev_badges.db
```

- To create tables (development only) you can either run Alembic migrations (recommended) or let SQLAlchemy create tables directly:

```bash
# Alembic
uv run alembic upgrade head

# --or-- create tables programmatically (not for production)
python -c "from services.badges.db import base, session; base.Base.metadata.create_all(bind=session.engine)"
```

Running locally

- Start the FastAPI server for the Badges Service:

```bash
export DATABASE_URL=sqlite:///./dev_badges.db
export BADGE_DIR=./tmp_badges
uv run uvicorn services.badges.main:app --reload --port 9001
```

- Start an RQ worker (if using Redis and background queue):

```bash
export REDIS_URL=redis://localhost:6379/0
# using rq CLI; make sure the queue name matches the code (badge_queue)
rq worker badge_queue
```

- Manual worker execution (helpful for debugging without Redis):

```bash
python -c "from services.badges.workers.badge_worker import process_badge_generation; process_badge_generation('<job-id>')"
```

Testing

- Unit tests (service-level):

```bash
uv run pytest tests/services/badges -q
```

- Integration E2E test (uses a temporary SQLite DB and temporary `BADGE_DIR`):

```bash
uv run pytest tests/integration/test_e2e_badge_service.py::test_e2e_generate_and_process -q
```

Troubleshooting

- "'str' object has no attribute 'hex'" or SQLAlchemy uuid conversion errors:
  - This appears when a UUID-type column is compared to a plain string. The `GET /badges/jobs/{job_id}` handler normalizes string `job_id` to a `uuid.UUID` for safe DB comparisons.

- No image files created in tests or locally:
  - Ensure `BADGE_DIR` environment variable is set or the default `badges` directory is writable. Tests set `BADGE_DIR` to a temporary directory; in local runs set `BADGE_DIR=./tmp_badges`.

- Alembic migrations don't detect badge models:
  - If your migrations are for the whole system, ensure the Alembic `env.py` imports and includes both the main app metadata and `services.badges.db.base.Base.metadata` in `target_metadata` so autogenerate sees badge tables.

- Database locked or concurrent access errors (SQLite):
  - SQLite has limited concurrency; for parallel worker/API testing use PostgreSQL or serialize operations in tests. SQLite `database is locked` errors usually indicate overlapping connections writing at the same time.

Deployment notes

- The service is designed to be deployed independently. Production deployments typically use:
  - A production DB (Postgres) specified in `DATABASE_URL`.
  - Redis for background queueing (`REDIS_URL`).
  - Shared or cloud storage for badges (instead of local `BADGE_DIR`) and a static file hosting solution.
  - A process manager to run: one or more API workers (`uvicorn`) and RQ worker processes.

Other notes

- Logs: worker and API modules use Python logging; configure logging in your deployment to capture `services.badges` logs.
- Extensibility: the image renderer and storage are designed to be swappable — replace `services.renderer.generate_badge_image` or `services.img_service.save_image` to integrate cloud storage or advanced rendering.

If you want, I can:
- Run the full test suite and fix any issues that appear.
- Add a small `docker-compose.yml` example to run the Badges Service with Postgres + Redis locally.
