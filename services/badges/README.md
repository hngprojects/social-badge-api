# Badges Service

Overview

The Badges Service is a small, self-contained HTTP service and worker that generates profile-style badge images for participants. It is designed to run separately from the main `app` service, sharing the same database (and optionally Redis) so it can be deployed independently while staying compatible with the main application.

Key responsibilities

- Accept badge generation requests via a lightweight HTTP API.
- Persist generation jobs to the database for durability and observability.
- Process queued jobs in a background worker: render an image, save it, and update job status.
- Serve badge image files from a filesystem directory (or cloud-backed storage if configured).

Architecture

- HTTP API (FastAPI): handles `POST /badges/generate` and `GET /badges/jobs/{job_id}`.
- Database (SQLAlchemy models in this package): a `BadgeGenerationJob` table stores job metadata, status, image URL, and error messages.
- Queue (RQ + Redis): enqueues job processing tasks; tests and local dev can call worker synchronously.
- Worker: `process_badge_generation(job_id)` renders, saves, and updates the DB record.
- Image rendering: uses `httpx` to fetch participant image and `Pillow` (PIL) to compose the badge.

API

- POST /badges/generate
  - Request: JSON body with `template_id`, `participant_name`, `photo_url` (see `services.badges.schemas.badge_schema.BadgeGenerateRequest`).
  - Response: { "job_id": "<uuid>", "status": "queued" }
  - Behavior: creates a `BadgeGenerationJob` row and enqueues the processing job.

- GET /badges/jobs/{job_id}
  - Response: { "job_id": "<uuid>", "status": "queued|processing|completed|failed", "badge_image_url": "/badges/..", "error_message": null }
  - Note: GET normalizes `job_id` to a UUID when possible to avoid DB comparison issues.

Environment variables

- `DATABASE_URL` (required): SQLAlchemy DB URL (e.g. `sqlite:///./badges.db` or a PostgreSQL DSN).
- `REDIS_URL` (optional for local dev, required for RQ): `redis://...`.
- `BADGE_DIR` (optional): local directory to save/rendered badge files (default `badges`).

Common commands (local development)

- Install repo dependencies (project root):

```bash
# from repo root
uv sync
# or create virtualenv and install
python -m venv .venv
source .venv/bin/activate
pip install -r services/badges/requirements.txt
pip install -e .
```

- Run only the Badges API (development):

```bash
# run from repo root
export DATABASE_URL=sqlite:///./dev_badges.db
export BADGE_DIR=./tmp_badges
uv run uvicorn services.badges.main:app --reload --port 9001
```

- Run worker (using RQ):

```bash
# ensure REDIS_URL is set
export REDIS_URL=redis://localhost:6379/0
# start worker (example using rq CLI)
rq worker badge_queue
# Or run worker module directly for manual processing
python -c "from services.badges.workers.badge_worker import process_badge_generation; process_badge_generation('<job-id>')"
```

Testing

- Unit tests (service-level):

```bash
uv run pytest tests/services/badges -q
```

- Integration test (end-to-end - uses a temp SQLite DB and temp BADGE_DIR):

```bash
uv run pytest tests/integration/test_e2e_badge_service.py::test_e2e_generate_and_process -q
```

Notes & troubleshooting

- UUID / DB comparisons: some SQLite setups or SQLAlchemy UUID columns may raise conversion errors when filtering a UUID column with a plain string. The GET route normalizes the `job_id` string to a `uuid.UUID` where possible before querying.
- File saving: the service uses `BADGE_DIR` environment variable. In tests we set `BADGE_DIR` to a tmp directory; in production mount a static files handler or use cloud storage.
- Alembic migrations: if you maintain migrations that span both the main app and this service, ensure Alembic `env.py` imports and includes both metadata objects (app + badges) to autogenerate correct schemas.

Contributing

- Follow repo style and run `uv run pytest` before opening PRs.
- Add unit tests for new renderer features or job lifecycle changes.

Files of interest

- `services/badges/routes/badges.py` — API endpoints
- `services/badges/workers/badge_worker.py` — job processor
- `services/badges/models/badge_model.py` — SQLAlchemy model for `BadgeGenerationJob`
- `services/badges/services/renderer.py` — image composition logic
- `services/badges/services/img_service.py` — image persistence

License

Follow the repository LICENSE.
