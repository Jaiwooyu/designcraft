import asyncio
import re
import time
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from conftest import complete

from render_api.app import UploadGate
from render_api.config import Settings
from render_api.models import RenderOptions


def submit(client, content=b"ok", **kwargs):
    response = client.post("/renders", files={"file": ("input.idml", content)}, **kwargs)
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_render_download_and_delete(api):
    with api() as (client, manager):
        assert client.get("/healthz").json() == {"status": "ok"}
        assert "/renders" in client.get("/openapi.json").json()["paths"]
        job_id = submit(client, data={"scale": "2", "fallback_font": "Malgun Gothic"})
        result = complete(client, job_id)
        assert result["status"] == "succeeded", result
        assert client.get("/renders?limit=1").json()[0]["id"] == job_id
        assert client.get("/renders?offset=1").json() == []
        assert client.get("/renders?limit=1000").status_code == 422
        assert result["warnings"] == ["test diagnostic"]
        assert result["options"]["scale"] == 2
        assert {item["name"] for item in result["files"]} == {"page-001.png", "layout.pdf"}
        assert client.get(f"/renders/{job_id}/files").json() == result["files"]
        for item in result["files"]:
            response = client.get(item["download_url"])
            assert response.status_code == 200
            assert response.headers["content-type"] == item["media_type"]
            assert len(response.content) == item["size"]
        assert client.get(f"/renders/{job_id}/files/input.idml").status_code == 404
        assert client.delete(f"/renders/{job_id}").status_code == 204
        assert not manager.directory(job_id).exists()
        assert client.get(f"/renders/{job_id}").status_code == 404


@pytest.mark.parametrize("format,names", [("png", {"page-001.png"}), ("pdf", {"layout.pdf"})])
def test_output_format(api, format, names):
    with api() as (client, _):
        result = complete(client, submit(client, data={"format": format}))
        assert result["status"] == "succeeded"
        assert {item["name"] for item in result["files"]} == names


def test_authentication(api):
    with api(token="test-secret") as (client, _):
        assert client.get("/healthz").status_code == 200
        assert client.post("/renders", files={"file": ("x.idml", b"ok")}).status_code == 401
        headers = {"Authorization": "Bearer test-secret"}
        job_id = submit(client, headers=headers)
        assert client.get(f"/renders/{job_id}").status_code == 401
        assert client.get("/renders").status_code == 401
        result = complete(client, job_id, headers=headers)
        url = result["files"][0]["download_url"]
        assert client.get(url).status_code == 401
        assert client.get(url, headers=headers).status_code == 200
        assert client.delete(f"/renders/{job_id}").status_code == 401
        assert client.delete(f"/renders/{job_id}", headers=headers).status_code == 204


@pytest.mark.parametrize(
    "data",
    [{"scale": "nan"}, {"scale": "5"}, {"format": "svg"}, {"fallback_font": "--pdf"}],
)
def test_invalid_options(api, data):
    with api() as (client, manager):
        response = client.post("/renders", files={"file": ("x.idml", b"ok")}, data=data)
        assert response.status_code == 422, response.text
        assert list(manager.jobs_dir.iterdir()) == []


def test_upload_limits_and_capacity(api):
    with api(max_upload_bytes=4, max_jobs=1) as (client, manager):
        assert client.post("/renders", files={"file": ("x.txt", b"ok")}).status_code == 415
        assert client.post("/renders", files={"file": ("x.idml", b"")}).status_code == 400
        assert client.post("/renders", files={"file": ("x.idml", b"12345")}).status_code == 413
        assert list(manager.jobs_dir.iterdir()) == []
        job_id = submit(client)
        complete(client, job_id)
        assert client.post("/renders", files={"file": ("x.idml", b"ok")}).status_code == 429
        assert client.delete(f"/renders/{job_id}").status_code == 204
        assert complete(client, submit(client))["status"] == "succeeded"


def test_renderer_failure_is_a_job_failure(api):
    with api() as (client, _):
        job_id = submit(client, b"fail")
        result = complete(client, job_id)
        assert result["status"] == "failed"
        assert "code 1" in result["error"]
        assert "invalid IDML" in result["logs"]
        assert result["files"] == []
        assert client.get(f"/renders/{job_id}/files").status_code == 409


def test_timeout_and_output_budget(api):
    with api(timeout_seconds=0.15) as (client, _):
        result = complete(client, submit(client, b"slow"))
        assert result["status"] == "failed"
        assert result["error"] == "Render time limit exceeded"
    with api(max_output_bytes=8) as (client, _):
        result = complete(client, submit(client))
        assert result["status"] == "failed"
        assert "size limit" in result["error"]


def test_bounded_stderr_does_not_deadlock(api):
    with api(max_log_bytes=1024) as (client, _):
        result = complete(client, submit(client, b"log"))
        assert result["status"] == "succeeded"
        assert result["logs_truncated"]
        assert len(result["logs"].encode()) <= 1024
        assert result["warnings"] == ["test diagnostic"]


def test_queued_and_running_cancellation(api):
    with api() as (client, _):
        first = submit(client, b"slow")
        second = submit(client, b"slow")
        assert client.get(f"/renders/{second}").json()["status"] == "queued"
        assert client.delete(f"/renders/{first}").status_code == 409
        for job_id in (second, first):
            assert client.post(f"/renders/{job_id}/cancel").status_code == 200
            assert complete(client, job_id)["status"] == "cancelled"
            assert client.delete(f"/renders/{job_id}").status_code == 204


def test_results_survive_restart_and_interrupted_jobs_fail(api):
    with api() as (client, manager):
        job_id = submit(client)
        complete(client, job_id)
        interrupted = manager.reserve(RenderOptions())
    with api() as (client, _):
        assert client.get(f"/renders/{job_id}").json()["status"] == "succeeded"
        old = client.get(f"/renders/{interrupted}").json()
        assert old["status"] == "failed"
        assert "restarted" in old["error"]
        assert client.get(f"/renders/{job_id}/files/layout.pdf").status_code == 200


def test_second_instance_refused(api):
    with api(), pytest.raises(RuntimeError, match="exactly one"), api():
        pytest.fail("second instance started")


def test_packaged_assets_reach_renderer(api):
    data = BytesIO()
    with ZipFile(data, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("input.idml", b"assets")
        archive.writestr("Links/nested/image.jpg", b"image")
        archive.writestr("Document Fonts/example.txt", b"font")
    with api() as (client, _):
        response = client.post("/renders", files={"file": ("package.zip", data.getvalue())})
        assert response.status_code == 202, response.text
        assert complete(client, response.json()["id"])["status"] == "succeeded"


def test_chunked_body_limit_before_parser(tmp_path):
    settings = Settings(renderer=Path("unused"), data_dir=tmp_path, max_upload_bytes=1)
    called = False
    messages = []

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    async def receive():
        return {"type": "http.request", "body": b"x" * (1024 * 1024 + 2), "more_body": True}

    async def send(message):
        messages.append(message)

    asyncio.run(
        UploadGate(inner, settings)(
            {"type": "http", "method": "POST", "path": "/renders", "headers": []}, receive, send
        )
    )
    assert not called
    assert messages[0]["status"] == 413


def test_real_renderer(api):
    """Exercise the actual native binary with the repository's public synthetic IDML."""
    root = Path(__file__).resolve().parents[3]
    renderer = root / "target/release/idml-render"
    if not renderer.is_file():
        renderer = renderer.with_suffix(".exe")
    if not renderer.is_file():
        pytest.skip("Build cargo build --release --locked to test the native renderer")
    source = (root / "crates/idml/src/tests.rs").read_text(encoding="utf-8")
    parts = dict(re.findall(r'const (\w+): &str = r#"(.*?)"#;', source, re.S))
    parts["SPREAD"] = re.sub(
        r'    <Rectangle Self="img".*?</Rectangle>', "", parts["SPREAD"], flags=re.S
    )
    entries = {
        "designmap.xml": "DESIGNMAP",
        "Resources/Graphic.xml": "GRAPHIC",
        "Resources/Styles.xml": "STYLES",
        "Resources/Preferences.xml": "PREFS",
        "MasterSpreads/MasterSpread_m1.xml": "MASTER",
        "Spreads/Spread_sp1.xml": "SPREAD",
        "Stories/Story_s1.xml": "STORY",
    }
    data = BytesIO()
    with ZipFile(data, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/vnd.adobe.indesign-idml-package")
        for name, key in entries.items():
            archive.writestr(name, parts[key])
    started = time.monotonic()
    with api(command=(str(renderer),)) as (client, _):
        result = complete(client, submit(client, data.getvalue()), timeout=30)
        assert result["status"] == "succeeded", result
        assert {item["name"] for item in result["files"]} == {
            "page-001.png",
            "page-002.png",
            "layout.pdf",
        }
        assert client.get(result["files"][0]["download_url"]).status_code == 200
    assert time.monotonic() - started < 30
