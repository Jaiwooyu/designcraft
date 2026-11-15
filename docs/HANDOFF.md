# 리팩터링 인수인계: DesignCraft → IDML 헤드리스 렌더러

기록 기준: 2026-11-15. 이 문서는 기존 DesignCraft의 `b2518507`과 리팩터링 후
`main`의 구현 상태를 비교한다. 변경 이력은 `ec00a43b`, `753eb1d7`, `03bacb4a`,
`37473d15`에서 확인할 수 있다.

## 변경 배경과 범위

사용자는 기사 내용을 IDML 지면에 채우고, 렌더한 결과를 에이전트가 보고 IDML을
수정해 다시 렌더하는 자동화를 만들고자 했다. 첫 단계는 서버에서 InDesign 없이
IDML을 PNG 또는 PDF로 렌더하는 프로그램이다. 기존 DesignCraft는 해당 렌더 기능을
이미 갖고 있었지만, 데스크톱 편집기·웹 앱·여러 파일 변환기와 편집 명령 엔진을
함께 관리하는 구조였다. 기존 CLI의 IDML 렌더도 `designcraft-engine`의 세션과
명령을 거쳐야 했다.

이번 변경은 **기존 조판 및 렌더 코드를 재사용하면서 실행 진입점과 워크스페이스를
헤드리스 렌더 용도로 전환한 것**이다. 사용자의 실제 신문 IDML과 그 옆의 PDF를
비교 자료로 사용했다. 사용자는 이미지 누락은 실제 워크플로에서 이미지가 제공될
것이므로 우선순위를 낮춰도 된다고 설명했다.

기사 내용 교체, IDML 파일 수정, 렌더 결과를 보는 에이전트, 수정·재렌더 반복은
**구현되지 않았다**. 원래 편집기와 그 명령 인터페이스도 제거됐으므로 이 기능들이
기존 앱에 남아 있다고 가정하면 안 된다.

## 저장소와 커밋

- 개인 포크: [Jaiwooyu/designcraft](https://github.com/Jaiwooyu/designcraft).
  로컬 `main`은 `fork/main`을 추적하며, `origin`은 원본 `storytold/designcraft`다.
- 사용자 요청에 따라 PR 없이 개인 포크 `main`에 직접 반영했다.
- `ec00a43b` — 렌더 전용 앱 추가, 워크스페이스와 파일 정리.
- `753eb1d7` — 사용하지 않는 기여자 데이터와 예전 도구 설정 삭제.
- `03bacb4a` — 이전 정리 과정에서 빠진 아이콘·브랜드 라이선스 문서 복원.
- `37473d15` — 초기 인수인계 문서 추가. 이 문서는 그 내용을 정정·상세화한다.

## 렌더 경로가 어떻게 바뀌었는가

| 단계 | 기존 CLI | 현재 `idml-render` |
|---|---|---|
| 문서 열기 | `Session`에서 `file.open` 명령 실행 | IDML 가져오기 라이브러리를 직접 호출 |
| 글꼴 | 엔진의 `font.list` / `font.replace` 명령으로 대체 가능 | 앱의 `fonts.rs`에서 누락 글꼴을 찾아 문서 메모리에서 대체 |
| PNG | 엔진 세션의 문서와 조판 캐시를 렌더러에 전달 | 가져온 문서와 조판 캐시를 렌더러에 직접 전달 |
| PDF | `file.exportPdf` 명령 실행 | PDF 내보내기 라이브러리를 직접 호출 |
| 기타 기능 | 편집 명령, 스크립트, MCP, 여러 포맷 내보내기 포함 | IDML 입력과 PNG/PDF 출력에 필요한 명령줄 옵션만 제공 |

현재 실행은 IDML을 읽고 링크와 문서 글꼴을 찾은 뒤, 누락 글꼴을 대체하고,
텍스트 넘침을 검사한다. 그다음 요청한 PNG 페이지를 순서대로 렌더하고 PDF를
생성한다. PNG와 PDF는 각각 별도로 요청할 수 있고 동시에 요청할 수도 있다.
출력은 `craft-atomic`을 통해 기록한다. 현재 실행 파일은 요청마다 한 프로세스를
실행하며, **페이지 단위 병렬 실행이나 PDF 병합을 구현하지 않았다**. 내부 렌더링
라이브러리의 병렬 처리와 앱 수준의 페이지 병렬 처리는 구분해야 한다.

기존 엔진이 하던 처리를 모두 옮긴 것은 아니다. 예를 들어 배치 PDF의 일부 비기본
크롭 처리와 부모 페이지의 일부 넘침 경고는 새 경로에서 불완전하다. 자세한 사항은
[렌더러 가이드](idml-render.md)와 [알려진 문제](gaps.md)에 기록돼 있다.

## 새로 추가하거나 수정한 주요 파일

| 파일 | 내용 |
|---|---|
| `apps/idml-render/Cargo.toml` | 렌더 전용 바이너리와 직접 필요한 라이브러리 의존성 정의 |
| `apps/idml-render/src/main.rs` | CLI 옵션, IDML·링크 읽기, 문서 글꼴 로드, 경고, PNG/PDF 출력 |
| `apps/idml-render/src/fonts.rs` | 스타일 상속을 반영해 사용 불가능한 글꼴을 메모리에서 대체 |
| `apps/idml-render/tests/render.rs` | 합성 IDML의 PNG/PDF 출력과 입력 파일 덮어쓰기 방지 검사 |
| `crates/fonts/src/fontdb/scoped.rs` | 이름에 `고딕`이 포함된 누락 글꼴의 한글 고딕 대체 경로 추가 |
| `crates/fonts/src/fontdb/tests/fallback.rs` | 한글 고딕 대체 회귀 테스트. 수정 없이 실패함을 확인 |
| `Cargo.toml`, `Cargo.lock` | 기본 빌드 대상을 `idml-render`로 변경하고 삭제된 앱의 의존성을 정리 |
| `xtask/src/main.rs`, `xtask/src/layers.rs` | 남은 워크스페이스의 검사 명령과 계층 분류로 변경 |
| `.github/workflows/ci.yml` | 공통 CI 워크플로만 유지하고 데스크톱용 시스템 패키지 목록 축소 |
| `AGENTS.md`, `README.md`, `ROADMAP.md`, `docs/gaps.md` | 새 프로젝트 범위와 사용·검증 규칙을 반영 |
| `ASSETS.md`, `assets/app-icon/LICENSE.txt`, `docs/brand/LICENSE-brand.txt` | 에셋 출처 기록을 정리하고 기존 법적 고지 문서 유지 |

`apps/idml-render/src/main.rs`에는 입력 IDML과 개별 링크에 대한 256 MiB 제한,
문서 폴더 밖 링크 차단, PDF 출력이 입력 IDML을 덮어쓰지 않도록 하는 검사도 있다.
`Document Fonts` 폴더는 대소문자를 구분하지 않고 찾는다. 누락 링크, 글꼴 대체,
일부 넘침과 PDF 경고는 stderr에 기록한다.

### 유지한 내부 크레이트

- `geom`, `color`: 좌표·도형 및 색상 기반.
- `doc`, `fonts`, `compose`: 문서 모델, 글꼴 탐색·셰이핑, 조판.
- `idml`, `images`, `render`, `pdf`: IDML 가져오기, 이미지 처리, PNG/PDF 렌더.

이 크레이트 내부의 기존 기능까지 모두 제거한 것은 아니다. 예를 들어 IDML 크레이트에는
가져오기 외의 코드가 남아 있고, PDF·이미지 코드에도 다양한 포맷과 출력 기능이 있다.
기본 실행 파일이 그 기능들을 사용자 명령으로 노출한다는 뜻은 아니다.

## 삭제한 항목

- 앱: `apps/designcraft`, `apps/designcraft-cli`, `apps/designcraft-web`.
- 내부 크레이트: `engine`, `ui-egui`, `tools`, `mcp`, `epub`, `pptx`, `textimport`, `format`.
- 데스크톱·웹 패키징, Nix 관련 파일, 앱 아이콘 이미지, 기존 UI 문서와 스크린샷.
- UI About 화면용 `contributors/` 데이터, 이전 CodeRabbit 및 nextest 설정.
- 예전 FreeBSD·Windows ARM·Nix·패키징·릴리스·SonarCloud·house-rules 워크플로.
  공통 CI 워크플로는 유지했다.
- 사용하지 않는 `xtask`의 아이콘·기능 비교·통계·버전 관련 모듈.

기존 앱 아이콘과 브랜드 이미지는 제거했지만, 해당 라이선스 문서 두 개는 사용자의
요청으로 복원했다. 루트 `LICENSE-*`, `NOTICE`, `licenses/`, `ASSETS.md`와 렌더에
사용되는 기존 라틴 폰트·하이픈 데이터·ICC 프로필도 유지했다. 새 폰트 파일이나
사용자가 제공한 실제 신문 파일은 커밋하지 않았다.

기준 커밋 `b2518507`부터 초기 인수인계 문서 커밋 `37473d15`까지의 Git diff는
**566개 파일 변경, 1,771줄 추가, 253,878줄 삭제**다. 이는 Git의 텍스트 diff 수치로,
바이너리 파일 크기나 실행 성능을 나타내지 않는다. 이 수치에는 문서 변경도 포함된다.

## 실행 방법

Rust 1.95 이상과 설치된 한글 고딕 계열 글꼴이 필요하다.

```sh
cargo build --release
./target/release/idml-render \
  --in input.idml \
  --png-dir output \
  --pdf output/layout.pdf
```

`--fallback-font 'Noto Sans CJK KR'`로 대체 글꼴을 지정할 수 있다. 생략하면 설치된
Apple SD Gothic Neo, Malgun Gothic, Noto Sans CJK KR, Noto Sans KR, Source Han
Sans K 순으로 찾는다. `--scale 2`는 PNG에서 포인트당 2픽셀이다. PNG에는 문서
도련이 포함되고 기본 PDF에는 도련과 재단선이 없다. 외부 링크는 IDML 옆이나 그
아래 `Links` 폴더에서 찾는다. 전체 사용법은 [렌더러 가이드](idml-render.md)를
참고한다.

## 최적화와 실제 측정

| 항목 | 관찰 결과 | 범위 |
|---|---|---|
| 바이너리 크기 | 기존 `designcraft-cli` 68,474,880바이트 → `idml-render` 45,303,872바이트, 약 33.8% 감소 | 같은 Mac의 당시 release 빌드 파일 크기. 배포 패키지나 메모리 사용량은 측정하지 않음 |
| 실제 예제 시간 | 새 렌더러로 3페이지 PNG와 PDF를 함께 출력한 실행에서 약 2.6~3.4초 | 단일 Mac, 제한된 실행 횟수. Linux·24면·동시 요청 성능은 측정하지 않음 |
| 이전 CLI 시간 | 같은 예제를 PNG와 PDF로 출력한 초기 실행에서 5.86초 | 초기 실행과 새 실행은 글꼴 대체 설정이 달라 엄밀한 속도 비교가 아님 |
| 출력 비교 | 같은 Apple SD Gothic Neo 대체 조건에서 이전 CLI와 새 앱의 PNG 3장 SHA-256 일치 | 이전 DesignCraft 출력과의 일치이며, 사용자가 제공한 기준 PDF와의 완전 일치는 아님 |

24면을 3페이지 측정값으로 단순 비례 계산하거나 병렬 작업 수로 나눈 숫자는 앞선
대화에서 추정한 값이다. 실제 24면이나 페이지 병렬 처리는 측정하지 않았으므로
확정된 처리 시간이나 속도 향상으로 해석하면 안 된다.

## 실제 신문 예제에서 확인된 상태

사용자가 제공한 IDML 패키지는 3페이지였고, 같은 폴더의 PDF를 시각적 기준으로
확인했다. 실제 신문 문서와 이미지는 저장소 밖에 있다.

- 누락 글꼴을 대체하기 전 PDF 출력에서는 5개 프레임에서 총 490자의 넘침 경고가
  나왔다. 모든 누락 글꼴을 Apple SD Gothic Neo로 대체한 실행에서는 두 프레임에
  총 25자가 남았다. 대체 글꼴의 폭과 스타일이 달라 글자 수와 줄바꿈은 변할 수 있다.
- 기준 PDF의 12면 하단 광고는 IDML이 참조하는 원본 링크 이미지가 제공된 폴더에
  없어 비어 있다. 경고에는 사용되지 않는 부모 페이지의 누락 링크도 포함될 수 있다.
- 기준 PDF와의 줄바꿈·폰트 스타일 차이는 남아 있으며, 전체 IDML 기능의 재현 여부는
  이 한 예제만으로 검증되지 않았다.

## 검사와 남은 상태

`cargo xtask ci`는 마지막 로컬 실행에서 포맷, PDF 의존성, Clippy, 워크스페이스
테스트, 에셋 출처, 계층 및 남은 라이브러리의 WASM 검사를 통과했다. 실제 예제는
정리 후 재실행해 PNG 3장의 해시 일치를 확인했다. 개인 포크의 원격 CI, Linux 서버
실행, 대용량 문서의 메모리 사용량과 병렬 렌더 성능은 확인하지 않았다.

현재 남은 기능·정확도 제한의 목록은 [docs/gaps.md](gaps.md)에 있다. 프로젝트
지시사항은 [AGENTS.md](../AGENTS.md), 리팩터링 이후 진행 기록은
[ROADMAP.md](../ROADMAP.md)에 있다.
