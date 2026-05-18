Setup — Badges Service

This document explains how to set up and run the Badges Service locally for development, testing, and simple deployments.

**⚠️ Important Caveat**: The Badges Service currently uses synchronous SQLAlchemy with SQLite for local development. To integrate with the main product's PostgreSQL database, this service needs to be refactored to use async SQLAlchemy drivers (`sqlalchemy[asyncpg]` for PostgreSQL+asyncpg). See [Deployment notes](#deployment-notes) for details.

Prerequisites

- Python 3.13
- Git
- Redis (for queueing with RQ) — optional for synchronous local testing
- `uv` development helper (used by this repo) or a Python virtualenv

Environment variables

- `DATABASE_URL` (required)
  - Example: `sqlite:///./dev_badges.db` or `postgresql+psycopg2://user:pass@localhost/dbname`
  - **Important**: Must be set in **every terminal** where you run the service or worker
- `REDIS_URL` (optional, defaults to `redis://localhost:6379/0`)
  - Example: `redis://localhost:6379/0`
- `BADGE_DIR` (optional, defaults to `./badges`)
  - Directory where generated badge files are saved. Must be writable.

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

1. **Set the database URL** (required before creating tables):

```bash
export DATABASE_URL=sqlite:///./dev_badges.db
```

2. **Create tables** (choose one method):

**Method A: Using Alembic (recommended for schema tracking)**
```bash
uv run alembic upgrade head
```

**Method B: SQLAlchemy direct (development only, not recommended for production)**
```bash
uv run python3 -c "from services.badges.models.badge_model import BadgeGenerationJob; from services.badges.db.base import Base; from services.badges.db.session import engine; Base.metadata.create_all(bind=engine)"
```

Running locally - Quick Start

**Terminal 1: API Server**
```bash
export DATABASE_URL=sqlite:///./dev_badges.db
export BADGE_DIR=./tmp_badges
mkdir -p ./tmp_badges
uv run uvicorn services.badges.main:app --reload --port 9001
```

**Terminal 2: Background Worker**
```bash
cd /home/vik/social-badge-api
export DATABASE_URL=sqlite:///./dev_badges.db
export REDIS_URL=redis://localhost:6379/0
uv run rq worker badge-generation
```

**Terminal 3: Test the API**
```bash
curl -X POST http://127.0.0.1:9001/badges/generate \
  -H "Content-Type: application/json" \
  -d '{
    "template_id": "template_001",
    "participant_name": "John Doe",
    "photo_url": "https://example.com/photo.jpg"
  }'
```

The response will contain a `job_id`. Check status with:
```bash
curl http://127.0.0.1:9001/badges/jobs/{job_id}
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

Common Issues & Troubleshooting

### Database not found / "no such table: badge_generation_jobs"
- **Cause**: Tables haven't been created yet or `DATABASE_URL` isn't set when creating tables
- **Fix**: Follow the "Database setup" section above and ensure you run the table creation command

### Worker doesn't process jobs / Queue is empty
- **Cause**: `DATABASE_URL` not set in worker terminal, or queue name mismatch
- **Fix**: 
  1. Verify in worker terminal: `echo $DATABASE_URL` should show `sqlite:///./dev_badges.db`
  2. If empty, set it: `export DATABASE_URL=sqlite:///./dev_badges.db`
  3. Verify queue name in code is `badge-generation` (not `badge_queue`)
  4. Restart worker: `uv run rq worker badge-generation`

### "'str' object has no attribute 'hex'" or UUID conversion errors
- **Cause**: String `job_id` being compared to UUID column without conversion
- **Fix**: The code now handles this automatically in both routes and workers
- **Note**: This is documented in the SETUP.md Troubleshooting section

### No image files created in tests or locally
- **Cause**: `BADGE_DIR` environment variable not set or directory not writable
- **Fix**: 
  - Ensure `BADGE_DIR` is set: `export BADGE_DIR=./tmp_badges`
  - Create directory if needed: `mkdir -p ./tmp_badges`
  - Verify permissions: `touch ./tmp_badges/test.txt`

### Alembic migrations don't detect badge models
- **Cause**: Alembic `env.py` not configured to include badge service models
- **Fix**: Ensure the Alembic `env.py` imports and includes both:
  - Main app metadata: `from app.db.base import Base`
  - Badge service metadata: `from services.badges.db.base import Base as BadgesBase`
  - And sets: `target_metadata = [Base.metadata, BadgesBase.metadata]`

### Database locked errors (SQLite only)
- **Cause**: SQLite has limited concurrency; overlapping connections writing at the same time
- **Fix**: 
  - For local testing: serialize operations (run tests sequentially)
  - For production: use PostgreSQL instead of SQLite

Deployment notes

The service is designed to be deployed independently. Production deployments typically use:
- A production DB (Postgres) specified in `DATABASE_URL`
- Redis for background queueing (`REDIS_URL`)
- Shared or cloud storage for badges (instead of local `BADGE_DIR`) and a static file hosting solution
- A process manager to run: one or more API workers (`uvicorn`) and RQ worker processes

**Important - Async Driver Migration**: To integrate this service with PostgreSQL:
1. Update [services/badges/db/session.py](services/badges/db/session.py) to use `create_async_engine` and `AsyncSession`
2. Convert route handlers in [services/badges/routes/badges.py](services/badges/routes/badges.py) to async
3. Update the worker in [services/badges/workers/badge_worker.py](services/badges/workers/badge_worker.py) to use `asyncio.run()` to bridge async DB code
4. Change `DATABASE_URL` from `postgresql+psycopg2://` to `postgresql+asyncpg://`

Other notes

- **Logs**: Worker and API modules use Python logging; configure logging in your deployment to capture `services.badges` logs
- **Extensibility**: The image renderer and storage are designed to be swappable — replace `services.badges.services.renderer.generate_badge_image` or `services.badges.services.img_service.save_image` to integrate cloud storage or advanced rendering
- **Queue Name**: The queue is named `badge-generation` (with hyphen), not `badge_queue`
