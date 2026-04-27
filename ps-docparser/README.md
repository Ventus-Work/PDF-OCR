# ps-docparser

PDF 기반 견적서/BOM 문서를 OCR → 구조화 JSON → Excel로 변환하는 파서 프로젝트입니다.

## 구조

- `engines/`: OCR 엔진 추상화와 팩토리
- `extractors/`: OCR 결과 추출, BOM/도면 메타 처리
- `parsers/`: Markdown/HTML 표 파싱과 섹션 정리
- `exporters/`: JSON/Excel 출력
- `pipelines/`: preset별 실행 경로
- `tests/`: 단위/통합 테스트와 fixture

## output 운영 기준

`output/`은 Git 추적 대상이 아니며, 실행 결과를 확인하기 위한 작업 폴더입니다.

- 기본 원칙: 매 실행 결과를 모두 쌓지 말고 대표 결과본만 유지
- 권장 보관 단위: 같은 문서에 대해 `md/json/xlsx` 한 세트만 남김
- 삭제 대상:
  - 중복 실행본
  - 임시 로그
  - coverage 파일
  - 테스트용 산출물

2026-04-23 기준 대표 결과본 예시:

- `20260423_고려아연 배관 Support 제작_추가_2차분 견적서.*`
- `20260423_260421_견적(R0)_대산 HD현대오일뱅크 10TON CRANE 설치_bom.*`
- `20260423_53-83 OKOK_1.*`
- `20260423_아연도금강판 견적서_1.*`

## BOM preset 자동 폴백과 대표본 정책

`--preset bom` 실행 시 fallback 정책은 `--bom-fallback`으로 선택합니다.

- `--bom-fallback auto`: 기본값. BOM/LINE LIST 대표본이 약하거나 혼합 견적 신호가 있을 때만 estimate 보조 산출물을 생성
- `--bom-fallback always`: 항상 estimate 보조 산출물을 생성
- `--bom-fallback never`: estimate 보조 산출물을 생성하지 않음
- `--no-bom-fallback`: 호환용 alias. 내부적으로 `--bom-fallback never`와 같은 의미

출력 규칙은 additive policy로 고정합니다.

- 대표본: `*_bom.md`, `*_bom.json`, `*_bom.xlsx`
- 보조본: `*_bom_fallback_estimate.md`, `*_bom_fallback_estimate.json`, `*_bom_fallback_estimate.xlsx`
- `RUN_MANIFEST.json`: 시스템 기준 실행 목록. 대표본은 `role=representative`, fallback estimate는 `role=diagnostic`으로 기록
- `RUN_SUMMARY.md`: 사람이 읽는 실행 요약
- estimate 결과를 대표본으로 승격하거나 merge하지 않음

배치 BOM 집계는 manifest의 `domain=bom`, `role=representative` 산출물을 우선 대상으로 삼으며, `_bom_fallback_estimate.json`은 집계하지 않습니다.

## 도메인/품질 계약

JSON section/table에는 downstream 판단용 최소 계약을 붙입니다.

- 공통: `domain`, `role`, `quality.status`, `quality.warnings`
- BOM: `primary_material_table`, `line_list_table`
- estimate: `estimate_table`, `detail_table`, `condition_table`
- pumsem: `pumsem_quantity_table`, `pumsem_size_table`, `pumsem_description_table`
- trade-statement 후보: `trade_statement_table`
- generic: `generic_table`

validator는 데이터를 수정하지 않고 quality metadata만 기록합니다. Excel exporter는 이 `domain/role`을 우선 사용하고, legacy JSON이나 분류 정보가 없는 table만 기존 header 기반 classifier fallback을 사용합니다.

## BOM 표 정합성 기준

BOM 전용 HTML 파서는 `rowspan`/`colspan`을 전개한 뒤 2행 헤더와 희소 행을 보정합니다.

- 자기 반복 헤더: `DESCRIPTION | DESCRIPTION`, `DWG NO. | DWG NO`는 단일 헤더로 축약
- 유의미한 복합 헤더: `자재중량 [Kg] | UNIT` 형식으로 보존
- 중복 헤더: 실제 서로 다른 열이면 `_2`, `_3` suffix로 보존
- 빈 헤더: `Column_N` fallback 이름 사용
- 실측 첫 행 보정: `수량`이 비고 `단위`에 숫자, 다음 UNIT 계열 열에 `식/EA/SET/LOT` 등이 들어간 경우만 한 칸 좌측 보정
- JSON row key와 Excel header는 같은 순서를 유지

각 BOM table에는 다음 품질 warning을 기록할 수 있습니다.

- header/key mismatch
- 자기 반복 복합 헤더
- 첫 row header 유출
- 수량/단위 밀림 의심
- 빈 tail column

BOM material table은 `BOM_자재표`, LINE LIST는 `BOM_LINE_LIST` 계열 sheet로 렌더링합니다.

## 실측 output 검증 도구

실측 PDF 결과는 실행 폴더를 분리해서 확인합니다.

```powershell
python tools/run_real_pdf_suite.py --output-root output --case-set 20260424_bom_backend
python tools/analyze_outputs.py output/실측테스트_YYYYMMDD_HHMMSS
```

- `tools/run_real_pdf_suite.py`: 대표 PDF 세트를 timestamp 폴더에 실행하고 summary/QA report를 생성
- `tools/analyze_outputs.py`: JSON/Excel/manifest 정합성, representative/diagnostic count, domain count, quality warning, header/key mismatch, bad composite header를 점검

## Google Drive 동기화 주의

이 프로젝트는 Google Drive 동기화 경로 안에서 운영되고 있습니다.

- 가능하면 한 PC에서만 Git 작업 수행
- 동기화 직후 `git status`로 예상치 못한 파일 변화를 먼저 확인
- `{GUID}...` 형식의 충돌 파일이나 0바이트 파일이 생기면 우선 확인 후 정리
- `.coverage`, 로그, 임시 파일은 커밋 전에 정리

## 테스트

전체 테스트:

```powershell
pytest
```

집중 테스트:

```powershell
pytest --no-cov tests/unit/parsers/test_bom_table_parser.py tests/unit/validators/test_output_quality.py tests/unit/extractors/test_bom_extractor.py tests/unit/pipelines/test_bom_pipeline.py tests/unit/cli/test_args.py tests/unit/exporters/test_excel_exporter.py tests/unit/utils/test_run_manifest.py tests/integration/test_bom_output_regression.py tests/integration/test_main_cli_bom_batch_aggregation_smoke.py
pytest --no-cov tests/integration/test_main_cli_bom_fallback_smoke.py tests/integration/test_main_cli_bom_smoke.py tests/integration/test_bom_markdown_e2e.py tests/integration/test_document_pipeline_bom_pdf_smoke.py tests/integration/test_main_cli_auto_route_smoke.py tests/unit/exporters/test_bom_aggregator.py tests/unit/test_detector.py tests/unit/pipelines/test_document_pipeline.py
pytest --no-cov tests/unit/validators/test_output_quality.py tests/unit/exporters/test_excel_exporter.py tests/unit/pipelines/test_document_pipeline.py tests/unit/tools/test_analyze_outputs.py tests/integration/test_main_cli_auto_route_smoke.py
```

`pytest.ini`에 전체 커버리지 게이트가 걸려 있으므로, 특정 파일만 빠르게 확인할 때는 `--no-cov`를 권장합니다.

## Phase15 로컬 웹 UI

Phase15는 기존 CLI 파서를 `FastAPI + React/Vite` 로컬 웹앱에서 실행하기 위한 MVP 계층입니다.

API 서버:

```powershell
uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
```

프론트 개발 서버:

```powershell
cd frontend
npm install
npm run dev
```

이 프로젝트는 Google Drive 동기화 경로에서 운영되므로, `frontend/node_modules`를 직접 설치하면 파일 잠금으로 `TAR_ENTRY_ERROR`가 반복될 수 있습니다. 그 경우 아래 로컬 작업 폴더 실행 스크립트를 사용합니다.

```powershell
.\scripts\frontend_local.ps1 build
.\scripts\frontend_local.ps1 dev
```

이 스크립트는 `frontend/` 소스를 `%LOCALAPPDATA%\Codex\ps-docparser-frontend-work`로 복사하고, npm 설치와 Vite 실행을 Drive 밖에서 수행합니다.

주요 API:

- `GET /api/config`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `GET /api/jobs/{job_id}/artifacts`
- `GET /api/jobs/{job_id}/artifacts/{artifact_id}`
- `GET /api/jobs/{job_id}/qa`

산출물은 `output/ui_runs/<job_id>/` 아래에 생성되며 Git 추적 대상이 아닙니다. v1은 기존 `main.py` CLI를 subprocess로 감싸고, 실행 후 `tools/analyze_outputs.py`로 QA 리포트를 생성합니다.

## 최근 유지보수 포인트

- BOM 복합 헤더를 `상위 | 하위` 형식으로 병합하고 자기 반복 헤더 제거
- BOM 희소 행 정렬, `Column_N` fallback, JSON/Excel header-row 정합성 회귀 테스트 추가
- 260421 BOM 첫 행 `수량/단위` 의미 밀림 보정 추가
- BOM/estimate/pumsem/trade-statement/generic table quality validator와 `domain/role/quality` 메타데이터 추가
- BOM preset 자동 폴백 정책을 `auto|always|never`로 명시화하고 manifest 기반 대표본/진단본 구분 추가
- 일반 DocumentPipeline 출력도 manifest representative로 기록
- analyzer의 manifest 대표본/진단본/domain count 보고 추가
- batch BOM 집계가 manifest의 representative BOM을 우선 사용하도록 정리
- 도면 메타데이터 추출기와 Excel `"도면_메타"` 시트 연동 완료
- 상세 백로그는 `../05_검증_리뷰/현재_개선작업_및_향후할일_20260424.md` 참고
