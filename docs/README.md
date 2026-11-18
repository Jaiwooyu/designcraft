# 문서 안내

`docs`에는 현재 사용하는 설명서만 둡니다.

| 목적 | 문서 |
|---|---|
| IDML → PNG/PDF 렌더링 | [렌더러 사용법](idml-render.md) |
| 파일·폴더의 서식 분석 JSON 생성 | [분석 옵션과 스키마](editorial-analysis.md) |
| 여러 호·면을 모아 편집 LLM용 자료 생성 | [편집 참고 라이브러리](editorial-library.md) |
| 지원하지 않는 기능과 정확도 한계 | [알려진 한계](gaps.md) |

## 로컬 신문 자료

현재 작업용 신문 패키지는 `corpus/newspapers/옥천신문/`에 호수별로 보관합니다.
`corpus/`는 Git에서 제외되는 로컬 입력 폴더이며, 원본 자료를 커밋하지 않습니다.
기존 패키지 안의 IDML·Links·Document Fonts·INDD·PDF·지침 파일은 함께 유지했습니다.
호수 폴더 이름은 `1859호`, `1860호`, `1861호`, `1862호`, `1863호`, `1867호`입니다.

저장소 루트에서 CMD로 전체 라이브러리를 만들려면:

```cmd
cargo build --release -p idml-render
python -X utf8 scripts\build_editorial_library.py --input ".\corpus\newspapers\옥천신문" --output ".\outputs\editorial-library" --newspaper "옥천신문"
```

IDML 파일만 분석 대상입니다. INDD만 있는 자료는 IDML로 내보낸 뒤 분석해야 합니다.
실행 결과는 Git에서 제외되는 `outputs/`에 저장합니다.
저장소 외부의 별도 입력·출력 경로를 지정해도 됩니다.

파이프라인이 완료되면 `outputs/editorial-library/editing_context.md`를 편집 AI의 참고 자료로
전달합니다. 실제 편집에는 원본 IDML·이미지·폰트·미리보기와 편집 지시가 함께 필요합니다.
사진·기사·캡션 관계 확정과 IDML 수정 기능은 아직 없습니다.
이미 분석한 출력이 있다면 재분석 없이 마지막 단계만 실행할 수 있습니다.

```cmd
python -X utf8 scripts\build_editing_context.py --library ".\outputs\editorial-library"
```

## 프로젝트 기록과 라이선스

- 진행 상황: [ROADMAP.md](../ROADMAP.md)
- 작업 지침: [AGENTS.md](../AGENTS.md)
- 에셋 출처: [ASSETS.md](../ASSETS.md)
- 법적 고지: [NOTICE](../NOTICE), [브랜드 라이선스](../licenses/brand/LICENSE-brand.txt)

초기 리팩터링 인수인계 문서는 현재 사용법과 중복되어 정리했습니다.
과거 내용은 Git 이력에서 확인할 수 있습니다.
