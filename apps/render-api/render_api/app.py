import asyncio
import hmac
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .jobs import CapacityError, JobConflict, JobManager
from .models import Artifact, RenderJob, RenderOptions
from .uploads import CHUNK, InvalidPackage, unpack

ERROR_DETAILS = {
    400: "빈 파일, 잘못된 ZIP 패키지 또는 잘못된 요청 헤더",
    401: "설정된 Bearer 토큰이 없거나 일치하지 않음",
    404: "작업 또는 결과 파일을 찾을 수 없음",
    408: "업로드 제한 시간 초과",
    409: "현재 작업 상태에서 요청을 수행할 수 없음",
    413: "업로드 파일 또는 요청 본문 크기 초과",
    415: "지원하지 않는 업로드 확장자",
    429: "동시 업로드 또는 저장 작업 수 한도 초과",
}


def error_responses(*codes):
    return {
        code: {
            "description": ERROR_DETAILS[code],
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["detail"],
                        "properties": {"detail": {"type": "string"}},
                    }
                }
            },
        }
        for code in codes
    }


def authorized(header: str, token: str) -> bool:
    scheme, _, supplied = header.partition(" ")
    return not token or (
        scheme.lower() == "bearer"
        and hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))
    )


class UploadGate:
    """Bound body bytes, upload duration and concurrent spooling before multipart parsing.

    Spool to a temporary file instead of buffering an entire request in RAM. Replay a
    capped body to FastAPI, whose multipart parser can then clean up normally on errors.
    """

    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings
        self.slots = threading.BoundedSemaphore(2)

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != "/renders"
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        if not authorized(
            headers.get(b"authorization", b"").decode("latin-1"), self.settings.token
        ):
            await JSONResponse(
                {"detail": "Invalid or missing bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return
        limit = self.settings.max_upload_bytes + 1024 * 1024  # bounded multipart overhead
        try:
            declared = int(headers.get(b"content-length", b"0"))
            if declared < 0:
                raise ValueError
        except ValueError:
            await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                scope, receive, send
            )
            return
        if declared > limit:
            await JSONResponse({"detail": "Request body exceeds the size limit"}, status_code=413)(
                scope, receive, send
            )
            return
        if not self.slots.acquire(blocking=False):
            await JSONResponse(
                {"detail": "Upload capacity reached; retry later"},
                status_code=429,
                headers={"Retry-After": "2"},
            )(scope, receive, send)
            return
        try:
            with tempfile.TemporaryFile() as body:
                total = 0
                deadline = time.monotonic() + self.settings.upload_timeout_seconds
                while True:
                    try:
                        message = await asyncio.wait_for(
                            receive(), max(0, deadline - time.monotonic())
                        )
                    except TimeoutError:
                        await JSONResponse({"detail": "Upload timed out"}, status_code=408)(
                            scope, receive, send
                        )
                        return
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    total += len(chunk)
                    if total > limit:
                        await JSONResponse(
                            {"detail": "Request body exceeds the size limit"}, status_code=413
                        )(scope, receive, send)
                        return
                    await run_in_threadpool(body.write, chunk)
                    if not message.get("more_body", False):
                        break
                body.seek(0)
                replayed = 0

                async def replay():
                    nonlocal replayed
                    if replayed < total:
                        chunk = await run_in_threadpool(body.read, CHUNK)
                        replayed += len(chunk)
                        return {
                            "type": "http.request",
                            "body": chunk,
                            "more_body": replayed < total,
                        }
                    if total == 0:
                        replayed = 1
                        return {"type": "http.request", "body": b"", "more_body": False}
                    return await receive()

                await self.app(scope, replay, send)
        finally:
            self.slots.release()


def create_app(settings: Settings | None = None, *, manager: JobManager | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    manager = manager or JobManager(settings)

    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(manager.start)
        try:
            yield
        finally:
            await run_in_threadpool(manager.stop)

    app = FastAPI(
        title="DesignCraft Render API",
        version="0.1.0",
        description=(
            "IDML 업로드 → 비동기 렌더 작업 → PNG/PDF 다운로드 API. "
            "IDML_API_TOKEN이 설정된 서버에서는 /renders 계열의 모든 요청에 "
            "Authorization: Bearer <token>이 필요합니다. "
            "202는 작업 접수 성공이며 렌더링 성공 여부는 작업 status로 확인합니다."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(UploadGate, settings=settings)
    bearer = HTTPBearer(auto_error=False)

    def authenticate(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        header = f"{credentials.scheme} {credentials.credentials}" if credentials else ""
        if not authorized(header, settings.token):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    router = APIRouter(dependencies=[Depends(authenticate)], tags=["renders"])

    @app.get(
        "/healthz",
        summary="worker 상태 확인",
        tags=["health"],
        responses={
            code: {
                "description": description,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["status"],
                            "properties": {"status": {"type": "string", "enum": [value]}},
                        }
                    }
                },
            }
            for code, description, value in (
                (200, "worker 정상; 렌더링을 직접 실행하는 검사는 아님", "ok"),
                (503, "worker 중지 또는 종료 처리 중", "unhealthy"),
            )
        },
    )
    def health():
        healthy = not manager.stopping and all(thread.is_alive() for thread in manager.threads)
        return JSONResponse(
            {"status": "ok" if healthy else "unhealthy"}, status_code=200 if healthy else 503
        )

    @router.post(
        "/renders",
        status_code=202,
        response_model=RenderJob,
        summary="IDML 업로드 및 렌더 작업 접수",
        description=(
            "multipart/form-data로 .idml 또는 패키지 .zip을 업로드합니다. "
            "ZIP 루트에는 IDML 1개, 선택적으로 Links/ 및 Document Fonts/를 넣습니다. "
            "기본 업로드 한도는 128 MiB입니다. 응답의 status_url을 조회해 완료를 확인합니다."
        ),
        responses=error_responses(400, 401, 408, 413, 415, 429),
    )
    async def render(
        file: Annotated[
            UploadFile, File(description="An IDML or a ZIP with IDML + Links + Document Fonts")
        ],
        format: Annotated[Literal["png", "pdf", "both"], Form()] = "both",
        scale: Annotated[float, Form(ge=0.1, le=4, allow_inf_nan=False)] = 1,
        fallback_font: Annotated[str | None, Form(min_length=1, max_length=128)] = None,
    ):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".idml", ".zip"):
            raise HTTPException(415, "Upload an .idml file or an IDML package .zip")
        try:
            options = RenderOptions(format=format, scale=scale, fallback_font=fallback_font)
        except ValidationError as error:
            raise HTTPException(422, error.errors(include_context=False)) from error
        try:
            job_id = await run_in_threadpool(manager.reserve, options)
        except CapacityError as error:
            raise HTTPException(429, str(error), headers={"Retry-After": "5"}) from error
        submitted = False
        try:
            directory = manager.directory(job_id)
            upload = directory / "upload.bin"
            written = 0
            with upload.open("xb") as output:
                while chunk := await file.read(CHUNK):
                    written += len(chunk)
                    if written > settings.max_upload_bytes:
                        raise HTTPException(413, "Uploaded file exceeds the size limit")
                    await run_in_threadpool(output.write, chunk)
            if written == 0:
                raise HTTPException(400, "Uploaded file is empty")
            if suffix == ".zip":
                try:
                    input_path = await run_in_threadpool(
                        unpack, upload, directory / "input", settings
                    )
                except (InvalidPackage, OSError, ValueError) as error:
                    raise HTTPException(400, str(error)) from error
                upload.unlink()
            else:
                input_path = directory / "input" / "document.idml"
                upload.replace(input_path)
            await run_in_threadpool(manager.submit, job_id, input_path)
            submitted = True
            return await run_in_threadpool(manager.get, job_id)
        finally:
            if not submitted:
                await run_in_threadpool(manager.discard, job_id)

    def job(job_id: UUID) -> RenderJob:
        try:
            return manager.get(job_id.hex)
        except KeyError as error:
            raise HTTPException(404, "Render job not found") from error

    @router.get(
        "/renders",
        response_model=list[RenderJob],
        summary="작업 목록 조회",
        description="최신 생성 순서의 배열입니다. 페이지네이션의 전체 개수는 반환하지 않습니다.",
        responses=error_responses(401),
    )
    def list_jobs(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0, le=1024)] = 0,
    ):
        return manager.list_jobs(limit, offset)

    @router.get(
        "/renders/{job_id}",
        response_model=RenderJob,
        summary="작업 상태와 진단 조회",
        responses=error_responses(401, 404),
    )
    def status(job_id: UUID):
        return job(job_id)

    @router.get(
        "/renders/{job_id}/files",
        response_model=list[Artifact],
        summary="성공한 작업의 결과 파일 목록",
        responses=error_responses(401, 404, 409),
    )
    def files(job_id: UUID):
        result = job(job_id)
        if result.status != "succeeded":
            raise HTTPException(409, "Render job has not succeeded")
        return result.files

    @router.get(
        "/renders/{job_id}/files/{filename}",
        response_class=FileResponse,
        summary="PNG 또는 PDF 다운로드",
        responses={
            **error_responses(401, 404, 409),
            200: {
                "description": "파일 바이너리; JSON이 아님",
                "content": {
                    media: {"schema": {"type": "string", "format": "binary"}}
                    for media in ("image/png", "application/pdf")
                },
            },
        },
    )
    def download(job_id: UUID, filename: str):
        result = job(job_id)
        if result.status != "succeeded":
            raise HTTPException(409, "Render job has not succeeded")
        artifact = next((entry for entry in result.files if entry.name == filename), None)
        if artifact is None:
            raise HTTPException(404, "Output file not found")
        path = manager.directory(job_id.hex) / "output" / artifact.name
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, "Output file is no longer available")
        return FileResponse(path, media_type=artifact.media_type, filename=artifact.name)

    @router.post(
        "/renders/{job_id}/cancel",
        response_model=RenderJob,
        summary="대기 작업 취소 또는 실행 중인 렌더러 종료 요청",
        description=(
            "queued는 cancelled로, running은 cancelling을 거쳐 cancelled로 전환됩니다. "
            "이미 종료된 작업과 uploading 작업은 현재 상태 그대로 반환합니다."
        ),
        responses=error_responses(401, 404),
    )
    def cancel(job_id: UUID):
        job(job_id)
        return manager.cancel(job_id.hex)

    @router.delete(
        "/renders/{job_id}",
        status_code=204,
        summary="종료된 작업과 입력·결과 파일 삭제",
        description="종료된 작업만 삭제할 수 있습니다. 성공 시 본문 없이 204를 반환합니다.",
        responses=error_responses(401, 404, 409),
    )
    def delete(job_id: UUID):
        job(job_id)
        try:
            manager.delete(job_id.hex)
        except (JobConflict, OSError) as error:
            raise HTTPException(409, str(error)) from error
        return Response(status_code=204)

    app.include_router(router)
    return app
