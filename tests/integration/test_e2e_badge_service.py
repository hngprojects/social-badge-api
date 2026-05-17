import os
import uuid
import importlib
from pathlib import Path
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def reload_badge_modules(tmp_path, monkeypatch):
    # Use a per-test SQLite database so the integration run is isolated from
    # the rest of the suite.
    tmp_db = tmp_path / "badges.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_db}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    # Ensure badges directory saved files go to tmp path
    badges_dir = tmp_path / "badges"
    badges_dir.mkdir()
    monkeypatch.setenv("BADGE_DIR", str(badges_dir))

    # Reload modules after env set so they pick up the per-test DB and badge dir.
    import services.badges.db.session as db_session
    importlib.reload(db_session)

    import services.badges.db.base as db_base

    import services.badges.models.badge_model as models

    import services.badges.services.img_service as img_service
    importlib.reload(img_service)

    import services.badges.services.renderer as renderer
    importlib.reload(renderer)

    import services.badges.services.queue as queue_mod
    importlib.reload(queue_mod)

    import services.badges.routes.badges as badges_routes
    importlib.reload(badges_routes)

    import services.badges.workers.badge_worker as worker_mod
    importlib.reload(worker_mod)

    # create tables
    engine = db_session.engine
    db_base.Base.metadata.create_all(bind=engine)

    return {
        "badges_dir": badges_dir,
        "db_session": db_session,
        "models": models,
        "img_service": img_service,
        "renderer": renderer,
        "queue_mod": queue_mod,
        "badges_routes": badges_routes,
        "worker_mod": worker_mod,
    }


def test_e2e_generate_and_process(monkeypatch, reload_badge_modules):
    """End-to-end: POST generate, worker processes job, job marked completed and file saved."""
    mods = reload_badge_modules
    badges_routes = mods["badges_routes"]
    worker_mod = mods["worker_mod"]
    img_service = mods["img_service"]
    renderer = mods["renderer"]
    models = mods["models"]
    db_session = mods["db_session"]

    app = FastAPI()
    app.include_router(badges_routes.router)

    client = TestClient(app)

    # Mock renderer to return a small PNG bytes buffer
    sample_png = BytesIO()
    # create a minimal PNG header to be saved; content itself is arbitrary for test
    sample_png.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    sample_png.seek(0)

    # Patch functions used by the worker directly (worker module imports these at import time)
    monkeypatch.setattr(worker_mod, "generate_badge_image", lambda url: BytesIO(sample_png.getvalue()))
    # delegate save_image to the real img_service.save_image so file is created
    monkeypatch.setattr(worker_mod, "save_image", lambda buf, filename: img_service.save_image(buf, filename))

    # Monkeypatch badge_queue.enqueue to immediately call worker synchronously
    def immediate_enqueue(func, job_id):
        # simulate background work by calling worker function directly
        # ensure UUID type for DB query when using UUID columns
        try:
            job_uuid = uuid.UUID(job_id) if isinstance(job_id, str) else job_id
        except Exception:
            job_uuid = job_id
        worker_mod.process_badge_generation(job_uuid)
        return None

    # Patch the badge_queue used by the route module so enqueue triggers immediate processing
    monkeypatch.setattr(badges_routes, "badge_queue", type("Q", (), {"enqueue": immediate_enqueue}))

    payload = {
        "template_id": "tpl_1",
        "participant_name": "Integration Tester",
        "photo_url": "https://example.com/avatar.png"
    }

    # POST to create job
    resp = client.post("/badges/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    job_id = data["job_id"]
    assert data["status"] in [s.value for s in mods["models"].JobStatus]

    # GET job should now show completed (since enqueue called worker)
    get_resp = client.get(f"/badges/jobs/{job_id}")
    assert get_resp.status_code == 200
    job_data = get_resp.json()
    if "status" not in job_data:
        pytest.fail(f"unexpected job data: {job_data}")
    assert job_data["status"] == "completed"
    assert "badge_image_url" in job_data

    # verify file exists
    badges_dir = mods["badges_dir"]
    files = list(badges_dir.iterdir())
    assert len(files) >= 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
