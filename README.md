# IDML 분석·편집 CLI와 신문 편집 참고 자료 생성기

InDesign에서 내보낸 IDML을 읽어 지면을 PNG·PDF로 렌더링하고, 서식과 배치를 분석하는 프로젝트입니다.
DesignCraft의 IDML 가져오기·조판·렌더링 라이브러리를 사용하는 Rust 프로그램과 Python 스크립트로 구성됩니다.
실행에 InDesign, 그래픽 창, GPU가 필요하지 않습니다.
`idml-render`는 렌더링·분석을, `designcraft-cli`는 명령과 스크립트를 통한 문서 편집을 담당합니다.
CLI 소스는 `cli/`, 공용 라이브러리는 `crates/`에 있으며 루트 Cargo 워크스페이스와 잠금 파일을 함께 사용합니다.

여러 호의 신문을 분석하면 면별 프로필, 유사 지면, 반복 서식 후보와
**편집 AI에 참고 자료로 전달할 `editing_context.md` 한 파일**까지 생성합니다.
기사 묶음 후보, 원본 본문 연결 순서, 사진·캡션 후보, 겹침·감싸기 관찰, 누락·넘침 상태도 함께 기록합니다.

`designcraft-cli`로 IDML을 읽고 텍스트·프레임·이미지·서식 등을 편집한 뒤 IDML·PDF·PNG로 내보낼 수 있습니다.
이는 자체 엔진으로 IDML 문서를 편집하는 기능이며 Adobe InDesign 앱을 직접 제어하는 기능은 아닙니다.
`.indd`·`.indt` 가져오기도 제공하지만 `.indd`로 저장하지는 않습니다. 실제 문서의 왕복 서식 보존은 별도 검토가 필요합니다.
LLM 호출, 사진·캡션·기사 관계 확정, 편집 후 자동 검증을 연결한 전체 자동 편집 파이프라인은 아직 없습니다.
Markdown만으로 이미지 관계와 편집 결과의 정확성을 보장할 수는 없습니다.

## 1. 실행 위치와 준비 사항

아래 명령은 모두 **이 README와 `Cargo.toml`이 있는 저장소 루트**에서 실행합니다.
경로는 전부 저장소 루트 기준 상대 경로이며, 명령 예시는 **Windows CMD 기준**입니다.
경로에 공백이나 한글이 있으므로 따옴표까지 복사하세요. 각 명령은 한 줄로 실행합니다.

| 준비 항목 | 필요한 작업 |
|---|---|
| Rust 1.95 이상과 Cargo | IDML 렌더러 빌드·실행 |
| Python 3.11 이상 | 라이브러리와 최종 Markdown 생성. 추가 Python 패키지는 필요 없음 |
| `.idml` 파일 | 분석 파이프라인의 원본 지면 입력. CLI는 `.indd` 가져오기도 제공하지만 실제 문서 보존 여부는 검토 필요 |
| `Links` 폴더와 이미지 | 사진·광고가 포함된 렌더링과 시각적 검토 |
| 원본 폰트 또는 설치된 대체 폰트 | 글자 표시·줄바꿈·넘침 계산 |

환경 확인:

```cmd
rustc --version
cargo --version
python --version
```

렌더러 빌드:

```cmd
cargo build --release -p idml-render
```

Windows 실행 파일은 `./target/release/idml-render.exe`에 생성됩니다.
처음에는 의존성 다운로드와 컴파일 때문에 오래 걸릴 수 있습니다.
코드가 바뀌지 않았다면 다음 빌드는 기존 결과를 재사용합니다.
이미 만든 라이브러리에서 최종 Markdown만 생성할 때는 Rust 빌드가 필요하지 않습니다.

## 2. 가장 자주 사용하는 두 가지 명령

### 여러 호의 IDML을 처음부터 분석하기

```cmd
python -X utf8 scripts\build_editorial_library.py --input ".\corpus\newspapers\옥천신문" --output ".\outputs\editorial-library" --newspaper "옥천신문"
```

- **입력:** `./corpus/newspapers/옥천신문/` 아래 호수별 IDML 패키지.
- **처리:** IDML 분석 → 면별 프로필 → 반복 서식·유사 지면 비교 → 최종 Markdown.
- **최종 결과:** `./outputs/editorial-library/editing_context.md`.
- 렌더러를 먼저 빌드해야 합니다. 이 명령 자체는 PNG·PDF를 생성하지 않습니다.

### 기존 분석 결과로 최종 전달물만 다시 만들기

```cmd
python -X utf8 scripts\build_editing_context.py --library ".\outputs\editorial-library"
```

- **입력:** 기존 출력 폴더의 `latest.json`, 해당 실행의 `library.json`, 프로필과 서식 후보.
- **처리:** 기존 결과를 읽어 한 파일로 정리합니다. IDML 재분석·렌더링·LLM 호출은 없습니다.
- **최종 결과:** `./outputs/editorial-library/editing_context.md`를 갱신합니다.
- 기존 분석 JSON과 `latest.json`은 변경하지 않습니다.

이미 분석을 마친 경우에는 두 번째 명령을 사용하면 됩니다.

### CLI로 문서 편집하기

별도 프로젝트에서 빌드할 필요 없이 저장소 루트에서 실행합니다.

```cmd
cargo build --release -p designcraft-cli
cargo run --release -p designcraft-cli -- --help
cargo run --release -p designcraft-cli -- commands
cargo run --release -p designcraft-cli -- describe story.setText
```

실행 파일은 `./target/release/designcraft-cli.exe`입니다. 여러 편집 명령은 UTF-8 스크립트에 적습니다.
예를 들어 `./outputs/edit.dcs`에 아래 내용을 저장하면 첫 번째 스토리의 본문을 교체합니다.
실제 문서에서는 먼저 `document.inspect` 결과를 확인해 대상 스토리 ID를 선택하세요.

```text
document.inspect
story.setText {"story":"$0.stories.0.id","text":"교체할 기사 본문"}
```

```cmd
cargo run --release -p designcraft-cli -- script ".\outputs\edit.dcs" --in ".\corpus\input.idml" --export ".\outputs\edited.idml" --export ".\outputs\edited.pdf" --export ".\outputs\edited.png"
```

- **입력:** 편집할 IDML, UTF-8 명령 스크립트, 연결된 이미지와 폰트.
- **결과:** 편집된 IDML과 PDF·PNG. 명령별 결과는 표준 출력의 JSON으로 반환됩니다.
- `--save`는 DesignCraft 고유 문서 저장용입니다. IDML 저장은 `--export "...idml"`을 사용합니다.
- `mcp` 서브명령은 AI 도구가 같은 편집 엔진을 호출하는 MCP 서버를 제공합니다.
- `app`·`--connect`는 별도로 실행 중인 DesignCraft 데스크톱 앱에 연결하는 기능입니다. 이 저장소는 데스크톱 앱을 포함하지 않습니다.

## 3. 입력 폴더 구성

문서 설명은 `docs/`, 로컬 입력은 `corpus/`, 생성 결과는 `outputs/`에 구분합니다.
`corpus/`와 `outputs/`는 Git에서 제외됩니다. 실제 신문·이미지·문서 폰트는 커밋하지 마세요.
이 폴더들의 실제 자료는 저장소를 새로 복제해도 포함되지 않습니다.

```text
프로젝트 루트/
├─ Cargo.toml
├─ README.md
├─ scripts/
│  ├─ build_editorial_library.py
│  └─ build_editing_context.py
├─ corpus/
│  └─ newspapers/
│     └─ 옥천신문/                  ← --input
│        ├─ 1859호/                 ← 호수 식별자
│        │  ├─ 1면 폴더/
│        │  │  ├─ 1면.idml
│        │  │  ├─ Links/
│        │  │  │  └─ 사진.jpg
│        │  │  └─ Document Fonts/
│        │  └─ 2면,3면 폴더/
│        │     ├─ 2면,3면.idml
│        │     └─ Links/
│        └─ 1860호/
│           └─ 1면.idml
├─ outputs/
│  └─ editorial-library/            ← --output
└─ docs/
```

한 번 실행할 때 한 신문만 넣습니다. 입력 루트 바로 아래 폴더 이름을 호수로 기록합니다.
`1230호/1면.idml`과 `1230호/1면/layout.idml` 모두 사용할 수 있습니다.
`--newspaper`는 결과에 기록할 신문 이름이며, 파일을 다른 신문과 자동 분류하는 옵션은 아닙니다.
신문이 다르면 입력·출력 폴더를 나눠 실행하세요.

IDML 옆의 `Links`와 `Document Fonts`를 함께 유지해야 합니다.
INDD·기준 PDF·지침 파일은 보관할 수 있지만 이 스크립트의 분석 입력으로 사용되지는 않습니다.
호수 폴더 안에 IDML이 없으면 그 호는 분석되지 않습니다.

입력과 출력은 서로 포함되지 않는 별도의 폴더여야 합니다.
예를 들어 `./corpus/newspapers/옥천신문/` 안에 출력 폴더를 만들면 오류가 납니다.

## 4. 전체 파이프라인과 결과 구조

```text
호수별 IDML 패키지
  → 기존 Rust 렌더러로 서식·배치 JSON 추출
  → 원본·호수·페이지가 연결된 프로필 생성
  → 기사 묶음·연결 순서·사진 관계·겹침과 감싸기·누락과 넘침 추출
  → 반복 서식 후보 집계와 유사 지면 검색
  → 면별 참고 문서 생성
  → 통합 전달물 editing_context.md 생성
```

실행할 때마다 새로운 `run-...` 폴더가 만들어집니다.
기존 실행 결과를 섞지 않고, 출력 루트에는 최신 통합 전달물도 따로 둡니다.
전체 파이프라인으로 생성되는 구조는 다음과 같습니다.

```text
outputs/editorial-library/
├─ editing_context.md              ← 최신 통합 전달물
├─ latest.json                     ← 최근 완료된 실행의 경로·성공/실패 수
└─ run-.../
   ├─ editing_context.md           ← 해당 실행의 통합 전달물 보관본
   ├─ README.md                    ← 면별 참고 문서로 이동하는 안내
   ├─ library.json                 ← 신문·호수·원본·페이지 색인과 실패 목록
   ├─ rule_candidates.json         ← 반복 서식·변형·빈도·대표 근거
   ├─ analyses/
   │  ├─ doc-....json              ← 원본 IDML 분석 결과
   │  └─ doc-....log               ← IDML 분석 경고·오류 로그
   ├─ structures/
   │  └─ doc-....json              ← 다섯 가지 구조 관찰과 후보·근거 전체
   ├─ profiles/
   │  └─ doc-.../
   │     └─ page-0001.json         ← 페이지별 서식·프레임·유사 지면
   └─ briefs/
      └─ doc-.../
         └─ page-0001.md           ← 해당 면 중심의 참고 자료
```

| 결과 | 사용 목적 |
|---|---|
| `editing_context.md` | 서식 후보·변형·면별 사례·품질 경고를 한 파일로 읽기 |
| `latest.json` | 어느 실행이 최근 결과인지 확인하기 |
| `library.json` | 원본 파일과 페이지 찾기, `page_id` 확인, 실패 원인 확인 |
| `rule_candidates.json` | 후보의 수치·빈도·근거를 구조화된 형태로 처리하기 |
| `analyses/*.json` | 원본 서식과 분석 당시의 렌더링 측정값 확인하기 |
| `structures/*.json` | 기사·사진·캡션 후보, 원본 연결 순서, 프레임 겹침·감싸기, 누락·넘침의 전체 근거 확인 |
| `profiles/*/*.json` | 페이지의 전체 관찰 프레임과 서식 확인하기 |
| `briefs/*/*.md` | 특정 면과 유사 지면의 표본을 가볍게 읽기 |

기존 결과에서 `build_editing_context.py`만 실행하면 지정한 출력 위치의 Markdown만 만듭니다.
새 실행 폴더를 만들거나 과거 실행의 보관본까지 자동 갱신하지는 않습니다.

## 5. 특정 면을 위한 최종 전달물

기본 `editing_context.md`는 신문 전체의 참고 문서입니다.
편집 대상 면을 지정하면 해당 면의 전체 프레임 좌표와 유사 사례·관련 서식으로 범위를 좁힐 수 있습니다.

먼저 `latest.json`이 가리키는 실행 폴더의 `library.json`에서
`pages[].page_id`를 확인합니다. 아래 `PAGE_ID`를 그 실제 값으로 바꾸세요.

```cmd
python -X utf8 scripts\build_editing_context.py --library ".\outputs\editorial-library" --page-id "PAGE_ID" --output ".\outputs\editing_context_target.md"
```

- **입력:** 기존 라이브러리와 선택한 `page_id`.
- **출력:** `./outputs/editing_context_target.md`.
- **내용:** 대상 면의 프레임 좌표, 대상·유사 지면의 서식, 관련 후보와 근거.

`page_id`는 가져오기 결과의 식별자입니다. `page_label`이 `1면`이어도 파일 내부 첫 페이지라는
뜻일 수 있으므로 원본 파일명을 함께 확인하세요. 여러 페이지가 들어 있는 IDML에서
파일 내부 순서와 실제 인쇄 면 번호가 일치한다고 단정하면 안 됩니다.

통합 문서는 기본 최대 512KiB입니다. 크기 한도를 조정하려면:

```cmd
python -X utf8 scripts\build_editing_context.py --library ".\outputs\editorial-library" --output ".\outputs\editing_context_large.md" --max-kib 1024
```

허용 범위는 32–1024KiB입니다. 초과하면 내용을 임의로 자르지 않고 오류를 반환하며 기존 파일은 유지합니다.
파일 크기 제한이 사용하는 LLM의 토큰 한도를 보장하지는 않습니다.

## 6. 이미 만든 분석 JSON에서 라이브러리 만들기

이 입력은 원본 IDML이 아니라 **분석 스키마 v1 JSON**입니다.
기존 JSON들로 집계와 문서 생성을 수행합니다.

```text
corpus/analysis-json/
├─ 1859호/
│  ├─ 1면.json
│  └─ 2면.json
└─ 1860호/
   └─ 1면.json
```

```cmd
python -X utf8 scripts\build_editorial_library.py --input ".\corpus\analysis-json" --output ".\outputs\editorial-library-from-json" --newspaper "옥천신문" --input-format json
```

최종 결과는 `./outputs/editorial-library-from-json/editing_context.md`입니다.
이 모드에는 Rust 빌드나 렌더러가 필요하지 않습니다.
완성된 라이브러리 폴더가 이미 있다면 `build_editing_context.py`로 마지막 단계만 실행하세요.

## 7. IDML 한 파일만 분석하기

아래 예시는 현재 로컬 신문 자료의 파일 경로를 사용합니다.
다른 파일을 분석하려면 `--in` 값만 바꾸세요.
JSON·PDF를 저장할 상위 폴더는 미리 만듭니다.

```cmd
if not exist ".\outputs\single" mkdir ".\outputs\single"
cargo run --release -p idml-render -- --in ".\corpus\newspapers\옥천신문\1859호\1면 폴더\1면.idml" --analysis ".\outputs\single\analysis.json"
```

| 항목 | 내용 |
|---|---|
| 입력 | `--in`으로 지정한 IDML과 옆의 이미지·문서 폰트 |
| 출력 | `./outputs/single/analysis.json` |
| `pages` | 페이지 크기, 여백·단 가이드, 관찰 요소의 위치·크기 |
| `stories[].spans` | 원본에 적용된 서체·크기·행간·자간·문단 설정 |
| `fonts` | 원본 서체의 사용 가능 여부와 대체 서체 |
| `candidates` | 같은 스타일·서식 조합의 관찰 사례 |
| `warnings`, `limitations` | 누락 링크와 분석 범위·정확도 한계 |

`cargo run`의 `--` 앞은 Cargo 옵션이고 뒤는 프로그램 옵션입니다.
컴파일이 필요하면 먼저 빌드한 뒤 실제 분석을 실행합니다.
프로그램 빌드만 수행하는 `cargo build`는 분석 JSON을 만들지 않습니다.

이미 빌드한 실행 파일을 직접 실행해도 같습니다.

```cmd
.\target\release\idml-render.exe --in ".\corpus\newspapers\옥천신문\1859호\1면 폴더\1면.idml" --analysis ".\outputs\single\analysis.json"
```

## 8. 한 폴더의 IDML을 모두 분석하기

이 기능은 **선택한 폴더 바로 아래**의 IDML만 처리합니다.
호수·면별 하위 폴더까지 읽으려면 2절의 Python 전체 파이프라인을 사용하세요.

```text
corpus/idml/
├─ 1면.idml
├─ 2면.idml
└─ Links/
```

```cmd
cargo run --release -p idml-render -- --in-dir ".\corpus\idml" --analysis-dir ".\outputs\analyses"
```

```text
outputs/analyses/
├─ 1면.json
└─ 2면.json
```

대문자 `.IDML`도 인식합니다. 입력 파일명에서 확장자를 바꿔 JSON을 저장하며 출력 폴더는 자동 생성합니다.
일부 파일이 실패해도 나머지를 처리하고 마지막에 성공·실패 개수를 출력합니다.
하나라도 실패하면 종료 코드는 0이 아닙니다. 출력 이름이 충돌하면 분석 전에 오류를 반환합니다.
폴더 모드는 `--png-dir`, `--pdf`, `--analysis`, `--scale`과 함께 사용할 수 없습니다.

## 9. 지면 PNG·PDF 만들기

서식 JSON만으로는 실제 사진 내용과 시각적 관계를 확인할 수 없습니다.
편집 대상 지면을 이미지로 확인하려면 별도로 렌더링합니다.

### PNG만 생성

```cmd
cargo run --release -p idml-render -- --in ".\corpus\newspapers\옥천신문\1859호\1면 폴더\1면.idml" --png-dir ".\outputs\preview" --scale 2
```

`./outputs/preview/page-001.png`, `page-002.png`처럼 파일 내부 페이지 순서대로 생성됩니다.
`--scale 2`는 포인트당 2픽셀입니다. PNG에는 도련이 포함됩니다.

### PDF만 생성

```cmd
if not exist ".\outputs\single" mkdir ".\outputs\single"
cargo run --release -p idml-render -- --in ".\corpus\newspapers\옥천신문\1859호\1면 폴더\1면.idml" --pdf ".\outputs\single\layout.pdf"
```

PDF 기본 출력에는 도련과 재단선이 없습니다.

### 분석 JSON·PNG·PDF를 함께 생성

```cmd
if not exist ".\outputs\single" mkdir ".\outputs\single"
cargo run --release -p idml-render -- --in ".\corpus\newspapers\옥천신문\1859호\1면 폴더\1면.idml" --analysis ".\outputs\single\analysis.json" --png-dir ".\outputs\single\pages" --pdf ".\outputs\single\layout.pdf"
```

출력 JSON과 PDF는 서로 다른 경로를 사용해야 합니다.
PNG 폴더는 자동 생성되지만 JSON·PDF를 저장할 상위 폴더는 준비되어 있어야 합니다.

## 10. 폰트와 이미지 입력

이미지는 IDML 옆 또는 그 아래 `Links`에서 찾습니다. `Links`의 하위 폴더도 지원합니다.
문서 폰트는 IDML 옆 `Document Fonts`에서 읽으며 폴더 이름의 대소문자는 구분하지 않습니다.
심볼릭 링크를 해석한 뒤에도 IDML 폴더 밖에 있는 에셋은 읽지 않습니다.

원본 폰트가 없으면 설치된 한글 대체 폰트를 찾습니다.
자동 선택은 Apple SD Gothic Neo, Malgun Gothic, Noto Sans CJK KR, Noto Sans KR,
Source Han Sans K 순입니다.
다음 예시는 **해당 서체가 실제로 설치된 경우에만** 사용합니다.

```cmd
cargo run --release -p idml-render -- --in ".\corpus\newspapers\옥천신문\1859호\1면 폴더\1면.idml" --png-dir ".\outputs\preview" --fallback-font "Malgun Gothic"
```

전체 파이프라인에도 같은 옵션을 전달할 수 있습니다.

```cmd
python -X utf8 scripts\build_editorial_library.py --input ".\corpus\newspapers\옥천신문" --output ".\outputs\editorial-library" --newspaper "옥천신문" --fallback-font "Malgun Gothic" --top-k 3 --timeout 120
```

대체 폰트는 줄바꿈과 넘침을 바꿀 수 있습니다.
분석 JSON은 대체 전에 원본 서식을 기록하고, 현재 폰트로 측정한 줄 수·넘침은 별도로 기록합니다.
이 측정값을 원본 InDesign이나 기준 PDF의 결과로 단정하면 안 됩니다.
새 폰트 파일은 저장소에 추가하지 않으며 선택적 빌드 폰트는 `storytold/craft-fonts`의 외부 입력입니다.
기존 번들 폰트의 출처와 라이선스는 [ASSETS.md](ASSETS.md)에 있습니다.

## 11. 편집 AI에 실제로 필요한 자료

`editing_context.md`는 사람이 읽고 AI에 전달하기 쉬운 **편집 참고 문서**입니다.
서식 수치와 대표 근거를 묶지만 원본 지면을 수정하는 데 필요한 모든 정보를 포함하지는 않습니다.

| 자료 | 필요한 이유 | 현재 상태 |
|---|---|---|
| 통합 Markdown | 반복 서식·변형·주의점 이해 | 자동 생성 |
| 원본 IDML | 프레임·텍스트·스타일과 실제 문서 구조 수정 | 사용자가 제공. `designcraft-cli`로 편집·내보내기 지원 |
| `Links` 이미지 | 사진 내용 확인, 교체, 원본 품질 유지 | 사용자가 제공. 렌더러가 읽음 |
| 원본 폰트 | 서식과 줄바꿈·텍스트 수용량 재현 | 외부 입력 |
| 지면 PNG 또는 기준 PDF | 사진·본문·제목의 시각적 균형 확인 | 렌더 명령으로 생성하거나 원본 제공 |
| 분석 JSON·대상 면 프로필 | 좌표·story/item 식별자와 원본 근거 조회 | 자동 생성 |
| 새 기사 원고와 편집 지시 | 바꿀 내용, 유지할 요소, 허용 범위 결정 | 사용자가 별도 제공 |
| 사진·캡션·기사 연결 및 배치 제약 | 어떤 요소를 함께 이동·교체할지 결정 | 의미 관계 자동 확정은 미구현 |

현재 분석은 이미지 프레임의 위치·크기, 텍스트 프레임과 story 연결 등 관찰 정보를 기록합니다.
파이프라인은 다음 다섯 항목을 `structures/*.json`, 페이지 프로필의 `editorial_structure`, 최종 Markdown에 연결합니다.

| 추출 항목 | 원본 사실과 후보의 구분 |
|---|---|
| 기사 단위 묶음 | 본문·역할 미정 story를 시작점으로 묶음 후보 생성. 확정 기사 수가 아님 |
| 읽는 순서 | 같은 story의 원본 프레임 연결 순서를 보존. 서로 다른 story 사이 순서는 미정 |
| 사진·캡션·기사 연결 | 스타일 힌트, 그룹, 간격·정렬을 근거로 후보를 최대 3개 유지 |
| 겹침·감싸기 | AABB 프레임 교차와 원본 wrap 설정. 실제 글리프 충돌 여부는 미정 |
| 누락·넘침 | 이미지 바이트 누락·미설치 서체와 story 전체의 렌더링 넘침·미측정 상태 |

원본에 live-caption 참조가 있으면 추정 후보와 구분해 기록합니다.
원본 잠금값은 사용자 수정 권한이 아니고, 기록된 이미지 링크는 검증된 로컬 파일 경로가 아닙니다.
관계를 찾지 못한 이미지는 캡션·기사 소속을 `unresolved`로 남깁니다.
문서별 비교·관계 수 제한에 걸리면 결과에 잘림 상태를 표시합니다.
예전 JSON에는 새 잠금·감싸기·크롭 정보가 없을 수 있어 미제공 상태를 유지합니다.
기존 프로필에 구조 분석 자체가 없다면 렌더러를 재빌드하고 전체 파이프라인을 다시 실행해야 새 정보를 얻을 수 있습니다.

그러나 **어떤 사진이 어느 기사에 속하는지, 어느 문장이 그 사진의 캡션인지,
어떤 크롭을 유지해야 하는지**까지 확정하지 않습니다. 실제 이미지 파일의 대응 정보와
배치 의도를 모두 확인한 편집용 관계 모델은 아직 없습니다.
유사 지면 검색 역시 프레임 배치와 서식을 비교하며 사진 픽셀·기사 의미를 해석하지 않습니다.

실제 AI 편집에는 다음 흐름이 필요합니다.

```text
원본 IDML + 이미지·폰트 + 지면 미리보기 + 분석 자료 + 사용자 편집 지시
  → 기사·사진·캡션의 관계 확인
  → IDML 편집 도구로 수정
  → 다시 렌더링
  → 넘침·겹침·사진과 캡션의 관계 확인
  → 필요한 부분 재수정
```

관계 확인, IDML 수정, 수정 후 검토를 연결하는 자동 편집 루프는 앞으로 구현할 부분입니다.
전달을 한 번에 하려면 Markdown과 원본 에셋·프로필·미리보기를 묶은 편집 패키지로 확장할 수 있습니다.
현재 스크립트는 그 ZIP 패키지를 자동 생성하지 않습니다.

## 12. 서식 후보와 지면 비교의 의미

| 우선순위 | 조건 | 활용 |
|---|---|---|
| `recurring` | 같은 문단·문자 스타일 쌍에서 80% 이상, 서로 다른 원본 내용 2개 이상·호수 폴더 2개 이상 | 먼저 검토할 기본값 후보 |
| `variant` | 여러 원본 내용에서 관찰되지만 위 조건을 충족하지 않음 | 반복되는 변형으로 보관 |
| `single_source` | 한 원본 내용에서 관찰 | 개별 사례로 보관 |

모두 검토가 필요한 관찰값입니다. 공통성이 높아도 사용자가 승인한 필수 편집 규칙이 되는 것은 아닙니다.
빈도는 서식 구간 수가 아니라 해당 스타일 쌍이 있는 고유 원본 내용·페이지 기준으로 계산합니다.
같은 면에서 여러 변형이 함께 사용될 수 있어 변형별 비율의 합이 100%를 넘을 수 있습니다.
바이트가 같은 입력만 중복 제거하며, 조금 수정한 템플릿은 별도로 집계될 수 있습니다.

지면 유형과 제목·본문·캡션 역할은 자동 확정하지 않습니다.
같은 스타일 이름에 여러 적용값이 있으면 변형으로 함께 보존합니다.
여러 면에 걸친 story의 서식은 `shared_story`로 남기고 면별 반복 집계에서는 제외합니다.

유사도는 판형, 프레임 영역 점유율, 원본 서식 집합, 단 가이드 수를 비교하는 초기 휴리스틱입니다.
유사도 점수를 편집 정책의 신뢰도나 기사·사진 관계가 맞다는 증거로 사용하면 안 됩니다.
자세한 집계 기준과 제한은 [라이브러리 설명서](docs/editorial-library.md)에 있습니다.

## 13. 주요 옵션과 처리 제한

| 도구 | 옵션 | 의미 |
|---|---|---|
| `idml-render` | `--in` | 단일 IDML 입력 |
| `idml-render` | `--analysis` / `--png-dir` / `--pdf` | JSON 파일 / PNG 폴더 / PDF 파일 출력 |
| `idml-render` | `--in-dir` / `--analysis-dir` | 한 폴더의 IDML을 파일별 JSON으로 분석 |
| `idml-render` | `--fallback-font` / `--scale` | 설치된 대체 폰트 / PNG 배율 |
| 라이브러리 스크립트 | `--input` / `--output` | 호수별 입력 폴더 / 라이브러리 출력 폴더 |
| 라이브러리 스크립트 | `--newspaper` | 한 실행의 신문 이름 |
| 라이브러리 스크립트 | `--input-format idml` 또는 `json` | 입력 종류. 기본값은 `idml` |
| 라이브러리 스크립트 | `--renderer` | 실행 파일 경로. 기본값은 `./target/release/idml-render.exe` |
| 라이브러리 스크립트 | `--top-k` | 유사 지면 수. 기본 3, 범위 1–5 |
| 라이브러리 스크립트 | `--timeout` | IDML 하나의 제한 시간. 기본 120초, 최대 3600초 |
| 최종 전달물 스크립트 | `--library` | 출력 루트, 실행 폴더, `library.json` 또는 `latest.json` |
| 최종 전달물 스크립트 | `--output` | 최종 Markdown 파일 경로 |
| 최종 전달물 스크립트 | `--page-id` | 편집 대상 면을 선택하는 식별자 |
| 최종 전달물 스크립트 | `--max-kib` | 최종 문서 크기 한도. 기본 512, 범위 32–1024 |

`--renderer`를 상대 경로로 지정하는 예:

```cmd
python -X utf8 scripts\build_editorial_library.py --input ".\corpus\newspapers\옥천신문" --output ".\outputs\editorial-library" --newspaper "옥천신문" --renderer ".\target\release\idml-render.exe"
```

네이티브 폴더 분석은 하위 폴더를 읽지 않으며 최대 1,000개 IDML을 처리합니다.
개별 입력 IDML과 연결 파일은 각각 최대 256MiB로 제한합니다.
라이브러리는 최대 1,000개 입력 파일, 전체 1,000페이지·50,000요소·50,000서식 레코드를 처리합니다.
일부 파일이 실패하면 계속 진행하고 실패 목록을 남기며 종료 코드는 0이 아닙니다.
부모 페이지·앵커 요소·표 셀·주석 등 분석에서 제외되는 내용도 있습니다.
폰트 가용성 검사는 글꼴 가족 기준이며 정확한 굵기·글리프와 원본 출력의 일치를 보증하지 않습니다.
전체 한계는 [알려진 한계](docs/gaps.md)와 [분석 스키마](docs/editorial-analysis.md)를 확인하세요.

## 14. 실행 상태 확인과 도움말

| 출력 메시지 | 의미 |
|---|---|
| `Finished release ...` | Rust 빌드 완료 |
| `[1/60] ...` | 입력 파일 분석 진행. 전체 개수는 입력에 따라 달라짐 |
| `Completed: ...` | 분석·자료 생성의 성공/실패 개수 요약 |
| `Library: ...` | 생성된 라이브러리 색인 경로 |
| `Editing context: ...` | 생성된 최종 Markdown 경로 |
| `FAILED ...` | 해당 파일 처리 실패. 전체 종료 코드와 실패 목록을 함께 확인 |

최신 실행 정보 확인:

```cmd
type ".\outputs\editorial-library\latest.json"
```

도움말:

```cmd
.\target\release\idml-render.exe --help
python -X utf8 scripts\build_editorial_library.py --help
python -X utf8 scripts\build_editing_context.py --help
```

분석 속도를 비교할 때는 빌드 시간과 실제 분석 시간을 구분하세요.
전체 파이프라인은 실행할 때마다 IDML을 다시 분석하며 이전 JSON을 자동 캐시로 재사용하지 않습니다.
기존 결과만 정리하려면 `build_editing_context.py`를 사용합니다.

## 15. 개발 검사

Python 스크립트와 실제 렌더러 연결 검사:

```cmd
python -X utf8 -m unittest discover -s scripts/tests -v
```

릴리스 렌더러가 있으면 합성 IDML의 실제 연동도 검사합니다.
없으면 해당 연동 검사는 건너뛰므로, 확인하려면 먼저 렌더러를 빌드하세요.

렌더러 테스트:

```cmd
cargo test -p idml-render
```

커밋 전 전체 Rust·에셋 검사:

```cmd
cargo xtask ci
```

포맷, PDF 의존성, Clippy, 워크스페이스 테스트, 에셋 출처, 의존 계층과 유지 라이브러리의 WASM 호환성을 확인합니다.
Python 테스트는 별도 명령으로 실행합니다.
WASM 검사를 위한 타깃이 없다면 먼저 설치합니다.

```cmd
rustup target add wasm32-unknown-unknown
```

## 16. 문서와 라이선스

- [단일 파일·폴더 분석과 JSON 스키마](docs/editorial-analysis.md)
- [호수·면별 라이브러리와 통합 전달물](docs/editorial-library.md)
- [알려진 한계](docs/gaps.md)
- [진행 상황](ROADMAP.md)
- [에셋 출처와 라이선스](ASSETS.md), [법적 고지](NOTICE)

프로젝트 코드는 [MIT](LICENSE-MIT) 또는 [Apache-2.0](LICENSE-APACHE) 라이선스로 제공됩니다.
폰트·이미지·프로필·브랜드 자료에는 별도 조건이 있을 수 있으므로 출처와 법적 고지를 유지해야 합니다.
원본 신문·문서 폰트 등 외부 자료의 권리는 각 권리자에게 있습니다.
