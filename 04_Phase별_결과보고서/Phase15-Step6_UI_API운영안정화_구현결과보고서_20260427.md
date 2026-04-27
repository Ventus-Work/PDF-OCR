# Phase15-Step6 UI/API 운영 안정화 구현 결과 보고서

작성일: 2026-04-27

대상 프로젝트: `Project/PJT_A/ps-docparser`

기준 문서: `03_Phase별_기술서/Phase15-Step6_UI_API운영안정화_상세개선기술서_20260427.md`

## 1. 구현 요약

Phase15-Step6의 UI/API 운영 안정화 항목 중 현재 MVP 운영에 직접 필요한 핵심 contract를 구현했다.

반영 내용:

- `generic/범용` 프리셋 정식 추가
- `preset=auto`에서 BOM fallback 선택값 전달
- 요청 엔진과 실제 적용 엔진 힌트 분리
- `JOB_STATUS.json` 기반 job 상태 저장/복구
- `GET /api/jobs` 최근 작업 목록 endpoint 추가
- CLI 종료 코드와 QA analyzer 종료 코드 분리
- 업로드 크기, 대기열, 동시 실행, 페이지 범위 검증 추가
- 프론트 문서 유형/엔진/상태/결과/로그 UI 보강
- 관련 API/CLI/Pipeline focused tests 추가

## 2. 주요 변경 파일

API/Backend:

- `api/schemas.py`
- `api/app.py`
- `api/jobs.py`
- `cli/args.py`

참고:

- `pipelines/document_pipeline.py`는 이번 Step6에서 직접 수정하지 않았다. 기존의 `explicit_preset is not None`이면 자동 라우팅을 건너뛰는 동작을 `--preset generic` contract로 활용했다.

Frontend:

- `frontend/src/api/client.ts`
- `frontend/src/App.tsx`
- `frontend/src/labels.ts`
- `frontend/src/components/UploadPanel.tsx`
- `frontend/src/components/JobStatusPanel.tsx`
- `frontend/src/components/ArtifactList.tsx`
- `frontend/src/components/LogViewer.tsx`
- `frontend/src/styles.css`

Tests:

- `tests/unit/api/test_app.py`
- `tests/unit/api/test_jobs.py`
- `tests/unit/cli/test_args.py`
- `tests/unit/pipelines/test_document_pipeline.py`

문서:

- `04_Phase별_결과보고서/Phase15-Step6_UI_API운영안정화_구현결과보고서_20260427.md`

## 3. API/CLI Contract 변경

### 3.1 Preset

기존:

```text
auto | bom | estimate | pumsem
```

변경:

```text
auto | generic | bom | estimate | pumsem
```

`generic`은 사용자가 자동 라우팅을 건너뛰고 범용 문서 경로를 강제하는 값이다.

### 3.2 Job Status

`JobStatusResponse`에 다음 필드를 추가했다.

```text
requested_engine
effective_preset
effective_engine
engine_note
cli_exit_code
analyzer_exit_code
stdout_tail
stderr_tail
```

기존 `exit_code`, `log_tail`은 호환을 위해 유지했다.

### 3.3 Jobs List

신규 endpoint:

```text
GET /api/jobs
```

`output/ui_runs/*/JOB_STATUS.json`을 읽어 최근 작업 목록을 반환한다.

### 3.4 JOB_STATUS.json

각 job 폴더에 상태 파일을 저장한다.

```text
output/ui_runs/<job_id>/JOB_STATUS.json
```

저장 내용:

- job id
- 상태
- 요청 preset/engine
- effective preset/engine 힌트
- 입력/결과/로그 상대 경로
- 실행 command
- created/started/finished timestamp
- CLI/analyzer/final exit code
- message

## 4. UI 변경

### 4.1 업로드 패널

- 문서 유형에 `범용` 추가
- 문서 유형별 설명 문구 추가
- OCR 엔진 자동 설명 추가
- 페이지 범위 즉시 검증 추가
- BOM 보조 산출물은 `자동` 또는 `BOM 도면`에서만 활성화
- 비활성화된 BOM fallback 값은 API 제출 시 `auto`로 정규화

### 4.2 작업 상태 패널

- 요청 엔진과 실제 엔진 표시 분리
- 실제 문서 유형 표시
- CLI 종료 코드와 QA 종료 코드 분리 표시
- 자동 엔진의 실제 의미를 `engine_note`로 표시

### 4.3 결과/로그

- 결과 탭을 대표 산출물, 진단 산출물, 기타 산출물로 그룹화
- 로그 탭은 stdout/stderr를 분리 표시
- 최근 작업 목록을 추가해 API 재시작 후 복구된 job도 선택 가능하게 했다

## 5. 검증 결과

### 5.1 API/CLI/Pipeline focused tests

명령:

```powershell
python -m pytest --no-cov tests/unit/api tests/unit/cli/test_args.py tests/unit/pipelines/test_document_pipeline.py
```

결과:

```text
51 passed
```

확인한 주요 시나리오:

- `/api/config`에 `generic` 포함
- `--preset generic` CLI 파싱
- `preset=generic`은 자동 라우팅을 건너뜀
- `preset=auto`, `bom_fallback=never`가 CLI command에 반영
- `preset=generic`에서는 BOM fallback 미전달
- `JOB_STATUS.json` 저장/복구
- CLI/analyzer exit code 분리
- 페이지 범위 오류 검증
- 업로드 크기 및 큐 제한 오류 검증

### 5.2 Frontend build

명령:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\frontend_local.ps1 build
```

결과:

```text
tsc -b && vite build
37 modules transformed
built
```

### 5.3 Diff check

명령:

```powershell
git diff --check
```

결과:

```text
PASS
```

## 6. 남은 위험

- 전체 `python -m pytest`는 이번 Step6 focused 검증에서는 실행하지 않았다. 최종 기준선 잠금 전에는 전체 회귀가 필요하다.
- 실측 PDF smoke는 아직 재실행하지 않았다. `53-83 OKOK.pdf`는 페이지 범위 `1-10`부터 확인하는 것이 안전하다.
- `effective_engine`은 v1에서 manifest의 실제 엔진 기록이 충분하지 않아 기본 설정 힌트 방식으로 표시한다. Pipeline이 실제 사용 엔진을 manifest에 기록하도록 추가 보강할 수 있다.
- 현재 워크트리에는 백엔드 안정화 변경과 Phase15 변경이 같이 섞여 있다. 커밋 전에는 백엔드 기준선, Step6 UI/API, 문서/보고서, 샘플 PDF 정리를 분리해야 한다.
- `.env`는 열람하지 않았다. 커밋 전 secret 포함 여부는 파일 목록 기준으로 별도 확인해야 한다.

## 7. 다음 권장 작업

1. 실제 웹 화면에서 `문서 유형=범용`, `문서 유형=자동 + BOM 보조 산출물=생성 안 함` 동작 확인
2. 실측 PDF `53-83 OKOK.pdf` 페이지 `1-10` smoke 실행
3. 전체 `python -m pytest` 실행
4. 워크트리 변경분을 기준선/Step6/문서/샘플 정리 단위로 분리
