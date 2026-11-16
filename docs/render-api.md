# Render HTTP API (FastAPI)

Client integration: [한국어 API 명세서](api-spec.md) · [OpenAPI JSON](openapi.json).

The `apps/render-api` service wraps the existing native `idml-render` executable. It accepts
uploads, returns a job ID immediately, queues work in SQLite and runs a bounded number of renderer
processes. Python handles HTTP and job management; the Rust composition/rendering libraries remain
unchanged. FastAPI was chosen for this small Python service and its upload/OpenAPI support. A
NestJS wrapper would also work when integrating with an existing TypeScript backend.

## Start locally

Build the native executable once, then install the wrapper's locked dependencies with
[uv](https://docs.astral.sh/uv/). Run these commands from the repository root:

```powershell
cargo build --release --locked
uv sync --project apps/render-api --locked
uv run --project apps/render-api --locked python -m render_api
```

The same commands work in a Linux shell. The default renderer is `target/release/idml-render.exe`
on Windows or `target/release/idml-render` on Linux, or an `idml-render` found on PATH. Override its
location with `IDML_RENDER_BIN`. Install a Korean font such as Noto Sans CJK KR on Linux; Korean
Windows can use Malgun Gothic. The API defaults to `http://127.0.0.1:8000`; interactive Swagger
documentation is at `/docs` and the OpenAPI schema is at `/openapi.json`.

For example, in PowerShell:

```powershell
$env:IDML_RENDER_BIN = 'D:\project\designcraft\target\release\idml-render.exe'
$env:IDML_API_TOKEN = 'replace-with-your-own-secret'
uv run --project apps/render-api --locked python -m render_api --port 8000
```

Use **one Uvicorn worker**, without `--reload`. The service holds an OS file lock on its data
directory and refuses another instance sharing that directory. `IDML_API_RENDER_WORKERS` controls
the number of renderer subprocesses, independently of the HTTP server's worker count.

## Submit and poll

```sh
curl -X POST http://127.0.0.1:8000/renders \
  -H "Authorization: Bearer replace-with-your-own-secret" \
  -F 'file=@input.idml' -F 'format=both' -F 'scale=1'

curl http://127.0.0.1:8000/renders/JOB_ID \
  -H "Authorization: Bearer replace-with-your-own-secret"
```

On Windows, use `curl.exe` to avoid the legacy PowerShell `curl` alias. `POST /renders` returns
HTTP 202 and a job object. Its status progresses from `queued` to `running`, then `succeeded`,
`failed` or `cancelled`. A very fast job may already be running or completed in the initial
response. Render failures are recorded in the job; they do not change the original HTTP 202.

The multipart fields are:

| Field | Meaning |
|---|---|
| `file` | Required `.idml` or package `.zip` upload |
| `format` | `png`, `pdf` or `both` (default) |
| `scale` | PNG pixels per point, finite and between 0.1 and 4; default 1 |
| `fallback_font` | Optional installed font family, e.g. `Malgun Gothic` or `Noto Sans CJK KR` |

For linked assets, upload a ZIP with exactly one IDML at the archive root:

```text
input.idml
Links/
  nested/image.jpg
Document Fonts/
  your-licensed-font.otf
```

The package has no outer containing folder. `Links` and `Document Fonts` use the spelling shown.
Subfolders are supported. Uploaded fonts are job-local inputs and never added to the repository
or installed system-wide. Raw IDML ZIP contents are interpreted by the renderer itself; the outer
package ZIP is extracted by the wrapper with separate file-count, path and expanded-size limits.
Stored and deflated ZIP entries are supported; ZIP64, multi-disk, encryption, duplicate paths,
symlinks, special files and paths unsafe on Windows or Linux are refused.

Successful jobs contain file metadata and relative download URLs, for example:

```json
{
  "id": "...",
  "status": "succeeded",
  "warnings": [],
  "logs_truncated": false,
  "files": [
    {
      "name": "layout.pdf",
      "media_type": "application/pdf",
      "size": 12345,
      "download_url": "/renders/.../files/layout.pdf"
    }
  ]
}
```

The full response also includes UTC timestamps, rendering options, bounded renderer stderr in
`logs`, an `error` for failures, and a `status_url`. `warnings` are warning-prefixed stderr lines;
these are diagnostic strings, not a complete structured preflight report. Missing fonts/images or
overset text can produce a successful job with warnings.

| Endpoint | Behavior |
|---|---|
| `GET /healthz` | Worker liveness; does not run a render; no authentication |
| `POST /renders` | Upload and enqueue; HTTP 202 |
| `GET /renders` | Newest jobs first; `limit` (1–100, default 20) and `offset` (0–1024) |
| `GET /renders/{id}` | Job state, diagnostics and output metadata |
| `GET /renders/{id}/files` | Output list after success; otherwise HTTP 409 |
| `GET /renders/{id}/files/{name}` | Download a named PNG/PDF after success |
| `POST /renders/{id}/cancel` | Cancel a queued job or request termination of a running renderer |
| `DELETE /renders/{id}` | Delete a terminal job and its inputs/outputs; active jobs return 409 |

Cancelling a running job briefly reports `cancelling`; wait for `cancelled` before deleting.
An unknown valid UUID returns 404; a malformed UUID returns 422. Invalid upload packages return
400, unsupported extensions 415, oversized uploads 413, invalid options 422, and full capacity 429.

## Configuration and operational limits

| Environment variable | Default |
|---|---|
| `IDML_RENDER_BIN` | PATH lookup, then the OS-specific `target/release/idml-render` |
| `IDML_API_DATA_DIR` | `outputs/render-api`, relative to the current working directory |
| `IDML_API_TOKEN` | Empty for local development; when set, bearer authentication on all render endpoints |
| `IDML_API_RENDER_WORKERS` | 1; range 1–8 |
| `IDML_API_MAX_JOBS` | 16 stored jobs, including completed and uploading jobs; range 1–1024 |
| `IDML_API_RENDER_TIMEOUT` | 300 seconds; range greater than 0 through 3600 |
| `IDML_API_LOG_LEVEL` | `info` |

Default per-job limits are a 128 MiB upload, 512 outer ZIP entries, 512 MiB unpacked package,
256 MiB per unpacked file, 256 MiB output, 128 output files and a 64 KiB stderr tail. The request
body allows another 1 MiB for multipart overhead. At most two uploads are spooled concurrently;
each body has a 60-second deadline, also when Content-Length is absent. A temporary request spool
and the multipart upload may coexist while processing. Change non-environment limits by supplying
a `Settings` instance to `create_app`.

Output quotas are monitored every 50 ms and checked again on completion, so a fast renderer may
temporarily exceed them. They do not impose hard RAM, CPU or disk limits: use container/OS limits
and storage quotas for a remotely exposed service. Bind locally by default; configure a token,
HTTPS and the appropriate reverse proxy before remote use. This version has a shared service
token, without user accounts, tenant isolation or a distributed queue.

Results and input documents remain on disk until DELETE; there is no automatic expiry. Full
storage capacity refuses new jobs until old ones are deleted. Queued jobs survive restart; jobs
interrupted during upload or rendering are marked failed rather than silently retried. SQLite
and files must be kept together on persistent local storage. Back up important outputs separately.

## Linux container

Build from the repository root (the Dockerfile builds the Linux Rust executable):

```sh
docker build -f apps/render-api/Dockerfile -t designcraft-render-api .
docker run --rm -p 127.0.0.1:8000:8000 \
  --memory=2g --cpus=2 --pids-limit=128 \
  -e IDML_API_TOKEN='replace-with-your-own-secret' \
  -v designcraft-render-data:/data designcraft-render-api
```

The image runs as UID/GID 10001 and installs Noto CJK fonts. With a bind mount, give this UID write
access to the mounted directory. The Docker build context excludes Git state, build outputs,
virtual environments, job data and optional external font checkouts. The repository's asset and
license notices are retained in the image. Container construction and Linux fidelity still need
validation on the deployment host.

## Verify

```sh
uv run --project apps/render-api --locked pytest apps/render-api/tests -q
uv run --project apps/render-api --locked ruff check apps/render-api
uv run --project apps/render-api --locked ruff format --check apps/render-api
cargo xtask ci
```

The Python suite covers requests, authentication, persisted jobs, cancellation, timeout/log/output
budgets and unsafe ZIP packages. It also runs a public synthetic IDML through the real native
executable when the release build is available; otherwise that test explicitly skips. No private
documents or new font assets are included. A separate GitHub Actions workflow runs wrapper checks
on Windows/Linux with Python 3.11/3.12; the native integration test skips there unless the release
executable is built first. The workflow itself has not yet been run on this branch remotely.

After changing dependencies, refresh the lock and Docker runtime dependency list:

```sh
uv lock --project apps/render-api
uv export --project apps/render-api --locked --no-dev --no-emit-project --format requirements-txt --output-file apps/render-api/requirements.txt
```
