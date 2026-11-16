# DesignCraft Render API 명세서

- API 버전: `0.1.0`
- 작성 기준: 2026-11-16, `feat/fastapi-render-wrapper`의 현재 구현
- 개발 서버 기본 주소: `http://127.0.0.1:8000`
- OpenAPI: [openapi.json](openapi.json), 서버 실행 시 `/openapi.json`
- Swagger UI: 서버 실행 시 `/docs`
- 설치·환경 변수·배포: [실행 안내](render-api.md)

IDML 문서를 업로드하고 비동기 작업의 상태를 조회한 뒤 PNG/PDF를 다운로드하는 API다.
기사 내용 교체나 지면 편집 API는 현재 제공하지 않는다.

## 1. 공통 규칙

### 인증

서버에 `IDML_API_TOKEN`이 설정돼 있으면 모든 `/renders` 요청에 다음 헤더가 필요하다.
토큰이 설정되지 않은 로컬 개발 환경에서는 생략할 수 있다. `/healthz`는 인증하지 않는다.

```http
Authorization: Bearer YOUR_TOKEN
```

### 요청과 응답

- 업로드만 `multipart/form-data`를 사용한다. 나머지 요청에는 본문이 필요하지 않다.
- 일반 응답은 `application/json`, 파일 다운로드는 `image/png` 또는 `application/pdf`다.
- 작업 ID는 응답에서 소문자 32자리 UUID hex 문자열로 반환한다. 경로 매개변수는
  하이픈이 있는 표준 UUID 문자열도 받으며 동일한 작업을 가리킨다.
- 날짜·시간은 UTC 기준 ISO 8601 문자열이다.
- `status_url`, `download_url`은 서버 기준 상대 경로다. 호출하는 서버 주소와 결합한다.
- `202 Accepted`는 작업 접수 성공이다. 렌더링 성공 여부는 반드시 `status`로 확인한다.

## 2. 엔드포인트 목록

| 메서드 | 경로 | 기능 | 정상 응답 |
|---|---|---|---|
| GET | `/healthz` | worker 상태 확인 | 200 |
| POST | `/renders` | 업로드 및 작업 접수 | 202, `RenderJob` |
| GET | `/renders` | 작업 목록 조회 | 200, `RenderJob[]` |
| GET | `/renders/{job_id}` | 작업 상태 조회 | 200, `RenderJob` |
| GET | `/renders/{job_id}/files` | 결과 파일 목록 | 200, `Artifact[]` |
| GET | `/renders/{job_id}/files/{filename}` | 결과 파일 다운로드 | 200, 파일 바이너리 |
| POST | `/renders/{job_id}/cancel` | 취소 요청 | 200, `RenderJob` |
| DELETE | `/renders/{job_id}` | 작업과 파일 삭제 | 204, 본문 없음 |

## 3. 렌더 작업 접수

`POST /renders`

**Content-Type:** `multipart/form-data`

| 필드 | 타입 | 필수 | 기본값 | 제약 |
|---|---|---|---|---|
| `file` | binary | 예 | — | `.idml` 또는 패키지 `.zip`, 최대 128 MiB |
| `format` | string | 아니요 | `both` | `png`, `pdf`, `both` |
| `scale` | number | 아니요 | `1` | 유한한 수, `0.1 ≤ scale ≤ 4` |
| `fallback_font` | string | 아니요 | 자동 선택 | 설치된 글꼴 이름, 1~128자 |

`scale`은 PNG의 포인트당 픽셀 수이며 PDF 출력에는 영향을 주지 않는다.
`fallback_font`는 공백만으로 구성하거나, 제어 문자를 포함하거나, `--`로 시작할 수 없다.
생략하면 렌더러가 사용 가능한 한글 대체 글꼴을 찾는다. 글꼴 파일 자체를 이 필드에 넣지 않는다.

```sh
curl -X POST 'http://127.0.0.1:8000/renders' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -F 'file=@input.idml' \
  -F 'format=both' \
  -F 'scale=1'
```

Windows PowerShell에서는 `curl` 대신 `curl.exe`를 사용하고, 여러 줄 연결 기호는
PowerShell 문법에 맞춰 사용하거나 명령을 한 줄로 입력한다. multipart boundary는 curl 등
HTTP 클라이언트가 생성하도록 하며 Content-Type 헤더를 수동으로 고정하지 않는다.

### 연결 이미지·문서 글꼴을 포함하는 ZIP

ZIP 루트에 IDML이 정확히 1개 있어야 한다. 외부 폴더로 한 번 더 감싸지 않는다.

```text
input.idml
Links/
  photo.jpg
  nested/advertisement.png
Document Fonts/
  licensed-font.otf
```

`Links`와 `Document Fonts`는 위 표기를 사용한다. 하위 폴더를 지원한다. 그 외의 루트 파일은
허용하지 않는다. 저장·Deflate 압축을 지원하며, 지원하지 않는 ZIP 레이아웃, 암호화,
중복 경로, 심볼릭 링크, 특수 파일, 경로 이동(`..`) 및 OS에서 안전하지 않은 경로는 거부한다.

### 접수 응답 예시

HTTP `202 Accepted`:

```json
{
  "id": "83a9b06c4fe34d7883d60cf07ec568ac",
  "status": "queued",
  "created_at": "2026-11-16T01:00:00Z",
  "updated_at": "2026-11-16T01:00:00Z",
  "options": {
    "format": "both",
    "scale": 1.0,
    "fallback_font": null
  },
  "warnings": [],
  "logs": "",
  "logs_truncated": false,
  "error": null,
  "files": [],
  "status_url": "/renders/83a9b06c4fe34d7883d60cf07ec568ac"
}
```

빠른 작업은 최초 응답에서 이미 `running` 또는 종료 상태일 수 있다. 원본 IDML의 내용이
잘못된 경우에도 접수가 성공하면 HTTP 202가 반환되고, 이후 작업이 `failed`로 종료될 수 있다.

주요 오류: `400`, `401`, `408`, `413`, `415`, `422`, `429`.

## 4. 작업 조회

### 목록

`GET /renders?limit=20&offset=0`

| 쿼리 | 타입 | 기본값 | 범위 |
|---|---|---|---|
| `limit` | integer | 20 | 1~100 |
| `offset` | integer | 0 | 0~1024 |

생성 시각 기준 최신 순서의 `RenderJob` 배열을 반환한다. `items`, `total` 같은 별도 래퍼는
없다. 결과가 없으면 `[]`다. 주요 오류: `401`, `422`.

### 개별 작업

`GET /renders/{job_id}`

작업 상태와 진단, 완료된 결과 파일 정보를 `RenderJob`으로 반환한다. 진행 중 상태에서는
주기적으로 재조회한다. `logs`와 `warnings`는 종료 시 저장되므로 실시간 로그 스트림이 아니다.
주요 오류: `401`, `404`, `422`.

### RenderJob

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | string | 작업 UUID hex |
| `status` | string | 아래 상태 표 참고 |
| `created_at` | datetime | 생성 시각, UTC |
| `updated_at` | datetime | 마지막 상태 갱신 시각, UTC |
| `options` | object | 접수한 `format`, `scale`, `fallback_font` |
| `warnings` | string[] | renderer stderr의 `warning:` 접두사를 제거한 경고 목록 |
| `logs` | string | renderer stderr의 마지막 부분, 기본 최대 64 KiB의 바이트에서 변환 |
| `logs_truncated` | boolean | 로그 앞부분이 용량 제한으로 잘렸는지 여부 |
| `error` | string 또는 null | 실패 원인. 성공 시 null |
| `files` | Artifact[] | 성공 시 생성된 파일 목록, 그 외에는 보통 빈 배열 |
| `status_url` | string | 상태 조회 상대 경로 |

| 상태 | 의미 | 삭제 가능 |
|---|---|---|
| `uploading` | 입력 파일 저장·패키지 처리 중 | 아니요 |
| `queued` | worker 실행 대기 | 아니요 |
| `running` | 렌더러 실행 중 | 아니요 |
| `cancelling` | 실행 중인 렌더러 종료 요청 처리 중 | 아니요 |
| `succeeded` | 요청한 결과 파일 생성 완료 | 예 |
| `failed` | 렌더 오류, 제한 초과 또는 서버 재시작으로 중단 | 예 |
| `cancelled` | 취소 완료 | 예 |

일반적인 진행은 `queued → running → succeeded/failed`다. 대기 작업은 바로 취소될 수 있고,
실행 중인 작업은 `cancelling`을 거쳐 `cancelled`로 전환된다.

글꼴 대체, 누락 이미지, 글 넘침 등은 경고를 남기면서 `succeeded`로 끝날 수 있다.
`succeeded`는 원본 InDesign과의 시각적 일치를 보장하지 않는다. 경고 문구는 구조화된
검사 코드가 아니므로 프로그램에서 특정 문구의 정확한 일치에 의존하지 않는다.

## 5. 결과 파일 조회·다운로드

### 파일 목록

`GET /renders/{job_id}/files`

작업이 `succeeded`이면 `Artifact[]`를 반환한다. 다른 상태는 실패·취소를 포함해 `409`다.
`GET /renders/{job_id}`의 `files` 필드와 같은 파일 목록이다.

```json
[
  {
    "name": "layout.pdf",
    "media_type": "application/pdf",
    "size": 12345,
    "download_url": "/renders/83a9b06c4fe34d7883d60cf07ec568ac/files/layout.pdf"
  },
  {
    "name": "page-001.png",
    "media_type": "image/png",
    "size": 67890,
    "download_url": "/renders/83a9b06c4fe34d7883d60cf07ec568ac/files/page-001.png"
  }
]
```

`size`는 파일 크기의 바이트 수이며 위 숫자는 예시다. PDF 이름은 `layout.pdf`, PNG는
`page-001.png`부터 시작한다. 클라이언트는 파일 이름을 추정하기보다 `download_url`을 사용한다.

### 다운로드

`GET /renders/{job_id}/files/{filename}`

성공 시 JSON 대신 파일 바이너리와 해당 `Content-Type`을 반환한다.
`Content-Disposition`은 attachment로 설정된다. 인증을 사용하는 서버에서는 다운로드에도
같은 Bearer 토큰을 전달해야 한다.

```sh
curl 'http://127.0.0.1:8000/renders/83a9b06c4fe34d7883d60cf07ec568ac/files/layout.pdf' \
  -H 'Authorization: Bearer YOUR_TOKEN' -o layout.pdf
```

파일 목록·다운로드의 주요 오류: `401`, `404`, `409`, `422`.

## 6. 취소·삭제

### 취소 요청

`POST /renders/{job_id}/cancel` — 요청 본문 없음.

HTTP 200과 갱신된 `RenderJob`을 반환한다. `queued`는 바로 `cancelled`, `running`은
`cancelling`을 거쳐 `cancelled`가 된다. 이미 종료된 작업 또는 `uploading` 작업은
현재 상태 그대로 반환하며, 취소 요청 자체가 파일을 삭제하지는 않는다.
주요 오류: `401`, `404`, `422`.

### 작업 및 저장 파일 삭제

`DELETE /renders/{job_id}` — 요청 본문 없음.

`succeeded`, `failed`, `cancelled` 작업만 삭제할 수 있다. 성공하면 HTTP 204와 빈 본문을
반환하며 입력·결과 파일과 작업 기록이 제거된다. 실행 중인 작업은 취소 후 `cancelled`를
확인하고 삭제한다. 삭제 완료 후 같은 작업을 조회하거나 다시 삭제하면 404다.
주요 오류: `401`, `404`, `409`, `422`.

## 7. 상태 확인

`GET /healthz` — 인증·요청 본문 없음.

- HTTP 200: `{"status":"ok"}`
- HTTP 503: `{"status":"unhealthy"}`

API worker의 생존 상태를 확인한다. 실제 IDML 렌더링이나 외부 링크·글꼴의 유효성을 검사하지는
않는다.

## 8. 오류 처리

일반 API 오류:

```json
{"detail":"Render job not found"}
```

입력 검증 오류는 `detail` 배열로 반환한다. 배열 원소의 부가 필드는 검증 라이브러리에 따라
달라질 수 있다.

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "file"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

| HTTP 상태 | 주요 원인 | 처리 |
|---|---|---|
| 400 | 빈 파일, 잘못된 패키지·요청 헤더 | 입력 수정 |
| 401 | 토큰 없음·불일치 | 인증 헤더 확인. `WWW-Authenticate: Bearer` 반환 |
| 404 | 작업·결과 파일 없음 | ID·파일명 확인 |
| 408 | 업로드 시간 초과 | 업로드 재시도 |
| 409 | 완료 전 다운로드, 실행 중 삭제, 파일 삭제 충돌 | 상태 재조회 후 요청 |
| 413 | 업로드 또는 본문 크기 초과 | 파일 크기 축소 |
| 415 | `.idml`, `.zip` 이외 확장자 | 지원 파일로 업로드 |
| 422 | 필수 필드 누락, 옵션·UUID·페이지네이션 검증 실패 | 요청 값 수정 |
| 429 | 동시 업로드 또는 저장 작업 수 한도 | `Retry-After` 이후 재시도, 완료 작업 삭제 |
| 503 | health worker 비정상 또는 HTTP 서버 수용 한도 | 상태·서버 용량 확인 |

동시 업로드 한도의 `Retry-After`는 2초, 저장 작업 수 한도는 5초다. 완료 작업도 저장 작업
수에 포함되므로 용량이 가득 찬 경우 기다리기만 해서는 해결되지 않고 작업 삭제가 필요하다.
예상하지 못한 서버·프록시 오류는 위 JSON 형식과 다를 수 있다.

렌더러 실행 실패나 실행 시간 초과는 보통 HTTP 오류가 아니라 `RenderJob.status="failed"`,
`error`, `logs`로 확인한다. 접수 요청을 자동 재전송하면 새 작업이 생긴다. 현재 멱등성 키나
자동 재시도 기능은 없다.

## 9. 기본 제한과 수명

| 항목 | 기본 제한 |
|---|---|
| 업로드 파일 | 128 MiB = 134,217,728 bytes |
| multipart 요청 본문 | 129 MiB, 헤더의 Content-Length 유무와 관계없이 측정 |
| 업로드 본문 수신 시간 | 60초 |
| 동시 업로드 처리 | 2개 |
| 저장 작업 수 | 16개, 완료·업로드 중 작업 포함 |
| 동시 렌더 프로세스 | 1개 |
| 렌더러 실행 시간 | 300초 |
| 외부 패키지 ZIP 항목 | 512개 |
| ZIP 압축 해제 크기 | 총 512 MiB, 개별 파일 256 MiB |
| 결과 파일 | 총 256 MiB, 최대 128개 |
| stderr 보관 | 마지막 64 KiB |

설정에 따라 제한은 달라질 수 있다. 출력 제한은 주기적으로 감시하므로 일시적으로 초과할 수
있으며 OS의 하드 자원 제한을 대신하지 않는다. 결과에 자동 만료는 없고 DELETE까지 보관한다.
재시작 시 대기 작업은 유지되며, 업로드·렌더링 중이던 작업은 `failed`로 표시된다.

## 10. 연동 순서

1. `POST /renders`로 파일을 전송하고 응답의 `id`, `status_url`을 저장한다.
2. `GET status_url`을 조회한다. 예를 들어 1초 간격으로 시작해 지연·부하에 따라 간격을 조정한다.
3. `succeeded`이면 `files[].download_url`로 필요한 파일을 받는다.
4. `failed`이면 `error`, `logs`, `warnings`를 확인한다. `cancelled`이면 다운로드를 중단한다.
5. 필요한 결과를 보관한 뒤 `DELETE /renders/{job_id}`로 서버 저장 공간을 반환한다.

OpenAPI JSON은 서버를 기동하거나 Rust를 다시 빌드하지 않고 갱신할 수 있다.

```sh
uv run --project apps/render-api --locked python -m render_api.export_openapi --output docs/openapi.json
```
