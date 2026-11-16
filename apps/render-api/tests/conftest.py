import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from render_api.app import create_app
from render_api.config import Settings
from render_api.jobs import JobManager


@pytest.fixture
def api(tmp_path):
    @contextmanager
    def launch(*, command=None, **overrides):
        settings = replace(
            Settings(renderer=Path(sys.executable), data_dir=tmp_path / "data"), **overrides
        )
        manager = JobManager(
            settings,
            command=command or (sys.executable, str(Path(__file__).with_name("fake_renderer.py"))),
        )
        with TestClient(create_app(settings, manager=manager)) as client:
            yield client, manager

    return launch


def complete(client, job_id, *, headers=None, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/renders/{job_id}", headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] in ("succeeded", "failed", "cancelled"):
            return result
        time.sleep(0.02)
    pytest.fail(f"Job {job_id} did not finish")
