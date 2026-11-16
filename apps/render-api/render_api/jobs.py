"""A bounded, persistent queue for one API instance and its renderer processes."""

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .models import Artifact, RenderJob, RenderOptions

LOGGER = logging.getLogger(__name__)
TERMINAL = {"succeeded", "failed", "cancelled"}
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
    options TEXT NOT NULL, logs TEXT NOT NULL DEFAULT '', truncated INTEGER NOT NULL DEFAULT 0,
    error TEXT, files TEXT NOT NULL DEFAULT '[]'
);
"""


class CapacityError(Exception):
    pass


class JobConflict(Exception):
    pass


class InstanceLock:
    """Refuse multiple API instances sharing this queue, also on Windows."""

    def __init__(self, path: Path):
        self.stream = path.open("a+b")
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            if path.stat().st_size == 0:
                self.stream.write(b"\0")
                self.stream.flush()
        except OSError as error:
            self.stream.close()
            raise RuntimeError(
                "Data directory is in use; run exactly one Uvicorn worker"
            ) from error

    def close(self):
        if self.stream.closed:
            return
        self.stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


class LogTail:
    def __init__(self, limit: int):
        self.limit = limit
        self.data = bytearray()
        self.truncated = False

    def drain(self, stream):
        with stream:
            while chunk := stream.read(4096):
                self.data.extend(chunk)
                if len(self.data) > self.limit:
                    self.truncated = True
                    del self.data[: len(self.data) - self.limit]


class JobManager:
    def __init__(self, settings: Settings, *, command: tuple[str, ...] | None = None):
        self.settings = settings
        self.root = settings.data_dir.resolve()
        self.jobs_dir = self.root / "jobs"
        self.command = command or (str(settings.renderer.resolve()),)
        self.condition = threading.Condition()
        self.stopping = False
        self.active: dict[str, threading.Event] = {}
        self.threads: list[threading.Thread] = []
        self.instance: InstanceLock | None = None

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.root / "jobs.sqlite3", timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start(self):
        if not Path(self.command[0]).is_file() or (
            os.name != "nt" and not os.access(self.command[0], os.X_OK)
        ):
            raise RuntimeError("Renderer not found; build it and configure IDML_RENDER_BIN")
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.instance = InstanceLock(self.root / ".instance.lock")
        try:
            with self.connection() as connection:
                connection.executescript(SCHEMA)
                connection.execute(
                    "UPDATE jobs SET status='failed', updated=?, error=? "
                    "WHERE status IN ('uploading', 'running', 'cancelling')",
                    (time.time(), "API restarted before this job completed"),
                )
            for number in range(self.settings.workers):
                thread = threading.Thread(target=self.worker, name=f"render-{number}", daemon=True)
                thread.start()
                self.threads.append(thread)
        except BaseException:
            self.stop()
            raise

    def stop(self):
        with self.condition:
            self.stopping = True
            for event in self.active.values():
                event.set()
            self.condition.notify_all()
        for thread in self.threads:
            thread.join(timeout=10)
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError("Renderer worker did not stop")
        if self.instance is not None:
            self.instance.close()

    def directory(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise KeyError(job_id)
        return self.jobs_dir / job_id

    def remove_directory(self, job_id: str):
        directory = self.directory(job_id)
        # Only server-generated UUID children of this configured root can be removed.
        if directory.is_symlink() or directory.resolve().parent != self.jobs_dir.resolve():
            raise JobConflict("Job directory is outside the configured storage")
        if directory.exists():
            shutil.rmtree(directory)

    def reserve(self, options: RenderOptions) -> str:
        with self.condition, self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("SELECT count(*) FROM jobs").fetchone()[0]
            if self.stopping or count >= self.settings.max_jobs:
                raise CapacityError(
                    "Job storage is full; delete completed jobs before submitting more"
                )
            job_id = uuid4().hex
            directory = self.directory(job_id)
            (directory / "input").mkdir(parents=True)
            (directory / "output").mkdir()
            now = time.time()
            connection.execute(
                "INSERT INTO jobs (id, status, created, updated, options) VALUES (?,?,?,?,?)",
                (job_id, "uploading", now, now, options.model_dump_json()),
            )
            return job_id

    def discard(self, job_id: str):
        with self.condition:
            self.remove_directory(job_id)
            with self.connection() as connection:
                connection.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def submit(self, job_id: str, input_path: Path):
        with self.condition, self.connection() as connection:
            relative = input_path.relative_to(self.directory(job_id)).as_posix()
            (self.directory(job_id) / "input-path.txt").write_text(relative, encoding="utf-8")
            connection.execute(
                "UPDATE jobs SET status='queued', updated=? WHERE id=? AND status='uploading'",
                (time.time(), job_id),
            )
        with self.condition:
            self.condition.notify_all()

    def get(self, job_id: str) -> RenderJob:
        self.directory(job_id)
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        logs = row["logs"]
        return RenderJob(
            id=job_id,
            status=row["status"],
            created_at=datetime.fromtimestamp(row["created"], UTC),
            updated_at=datetime.fromtimestamp(row["updated"], UTC),
            options=RenderOptions.model_validate_json(row["options"]),
            warnings=[
                line[8:].strip() for line in logs.splitlines() if line.startswith("warning:")
            ],
            logs=logs,
            logs_truncated=bool(row["truncated"]),
            error=row["error"],
            files=json.loads(row["files"]),
            status_url=f"/renders/{job_id}",
        )

    def list_jobs(self, limit: int, offset: int) -> list[RenderJob]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT id FROM jobs ORDER BY created DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
        results = []
        for row in rows:
            try:
                results.append(self.get(row["id"]))
            except KeyError:
                # A concurrent DELETE may remove a job after the initial query.
                continue
        return results

    def cancel(self, job_id: str) -> RenderJob:
        with self.condition:
            job = self.get(job_id)
            if job.status in ("queued", "running", "cancelling"):
                status = "cancelled" if job.status == "queued" else "cancelling"
                if event := self.active.get(job_id):
                    event.set()
                with self.connection() as connection:
                    connection.execute(
                        "UPDATE jobs SET status=?, updated=? WHERE id=?",
                        (status, time.time(), job_id),
                    )
            return self.get(job_id)

    def delete(self, job_id: str):
        with self.condition:
            if self.get(job_id).status not in TERMINAL:
                raise JobConflict("Cancel the job and wait for it to stop before deleting it")
            self.discard(job_id)

    def claim(self):
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM jobs WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id = row["id"]
            connection.execute(
                "UPDATE jobs SET status='running', updated=? WHERE id=?", (time.time(), job_id)
            )
            event = threading.Event()
            self.active[job_id] = event
            return job_id, event

    def worker(self):
        while True:
            with self.condition:
                while not self.stopping:
                    claimed = self.claim()
                    if claimed:
                        break
                    self.condition.wait()
                else:
                    return
            job_id, event = claimed
            try:
                self.render(job_id, event)
            except Exception:
                LOGGER.exception("Render worker failed for %s", job_id)
                with self.connection() as connection:
                    connection.execute(
                        "UPDATE jobs SET status='failed', updated=?, error=? WHERE id=?",
                        (time.time(), "Internal rendering worker error", job_id),
                    )
            finally:
                with self.condition:
                    self.active.pop(job_id, None)

    def output_entries(self, directory: Path):
        entries = []
        total = 0
        with os.scandir(directory) as iterator:
            for entry in iterator:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        raise ValueError("Unexpected directory or special file in renderer output")
                    size = entry.stat(follow_symlinks=False).st_size
                except FileNotFoundError:
                    # craft-atomic can rename a temporary output during this scan.
                    continue
                total += size
                entries.append(Path(entry.path))
                if total > self.settings.max_output_bytes:
                    raise ValueError("Renderer output exceeds the size limit")
                if len(entries) > self.settings.max_output_files:
                    raise ValueError("Renderer output exceeds the file count limit")
        return sorted(entries)

    def artifacts(self, job: RenderJob, directory: Path) -> list[Artifact]:
        artifacts = []
        for path in self.output_entries(directory):
            is_pdf = path.name == "layout.pdf"
            is_png = re.fullmatch(r"page-[0-9]{3,}\.png", path.name) is not None
            if not (is_pdf or is_png):
                raise ValueError("Renderer left an unexpected or incomplete output file")
            with path.open("rb") as stream:
                header = stream.read(8)
            if not (header.startswith(b"%PDF") if is_pdf else header == b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Renderer produced an invalid output file")
            artifacts.append(
                Artifact(
                    name=path.name,
                    media_type="application/pdf" if is_pdf else "image/png",
                    size=path.stat().st_size,
                    download_url=f"/renders/{job.id}/files/{path.name}",
                )
            )
        names = [artifact.name for artifact in artifacts]
        if job.options.format != "png" and "layout.pdf" not in names:
            raise ValueError("Renderer did not produce the requested PDF")
        if job.options.format != "pdf" and not any(name.endswith(".png") for name in names):
            raise ValueError("Renderer did not produce the requested PNG pages")
        return artifacts

    def render(self, job_id: str, cancelled: threading.Event):
        job = self.get(job_id)
        directory = self.directory(job_id)
        relative = (directory / "input-path.txt").read_text(encoding="utf-8")
        input_path = (directory / relative).resolve()
        if not input_path.is_relative_to((directory / "input").resolve()):
            raise ValueError("Invalid stored input path")
        output = directory / "output"
        arguments = [*self.command, "--in", str(input_path)]
        if job.options.format != "pdf":
            arguments += ["--png-dir", str(output), "--scale", str(job.options.scale)]
        if job.options.format != "png":
            arguments += ["--pdf", str(output / "layout.pdf")]
        if job.options.fallback_font is not None:
            arguments += ["--fallback-font", job.options.fallback_font]
        tail = LogTail(self.settings.max_log_bytes)
        process = None
        reader = None
        error = None
        files = []
        status = "failed"
        try:
            process = subprocess.Popen(
                arguments,
                cwd=directory,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            reader = threading.Thread(target=tail.drain, args=(process.stderr,), daemon=True)
            reader.start()
            deadline = time.monotonic() + self.settings.timeout_seconds
            while process.poll() is None:
                if cancelled.is_set():
                    status = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    error = "Render time limit exceeded"
                    break
                self.output_entries(output)
                cancelled.wait(0.05)
            if cancelled.is_set():
                status = "cancelled"
            elif error is None and process.poll() == 0:
                files = self.artifacts(job, output)
                status = "succeeded"
            elif error is None:
                error = f"Renderer exited with code {process.poll()}"
        except (OSError, ValueError) as exception:
            error = str(exception)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
            if reader is not None:
                reader.join(timeout=5)
                if reader.is_alive():
                    raise RuntimeError("Renderer log reader did not stop")
        with self.condition, self.connection() as connection:
            # A cancellation racing with a fast successful exit still wins.
            if cancelled.is_set():
                status, files, error = "cancelled", [], None
            connection.execute(
                "UPDATE jobs SET status=?, updated=?, logs=?, truncated=?, error=?, files=? "
                "WHERE id=?",
                (
                    status,
                    time.time(),
                    tail.data.decode("utf-8", errors="replace"),
                    int(tail.truncated),
                    error,
                    json.dumps([item.model_dump() for item in files]),
                    job_id,
                ),
            )
