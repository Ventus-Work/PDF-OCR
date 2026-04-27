# Phase15-Step6 UI/API 운영 안정화 상세 개선 기술서

작성일: 2026-04-27

대상 프로젝트: `Project/PJT_A/ps-docparser`

선행 단계:

- `Phase15-Step1_FastAPI_API어댑터_상세구현기술서_20260427.md`
- `Phase15-Step2_Job실행상태관리_상세구현기술서_20260427.md`
- `Phase15-Step3_결과QA조회다운로드_상세구현기술서_20260427.md`
- `Phase15-Step4_ReactVite_UI_상세구현기술서_20260427.md`
- `Phase15-Step5_통합검증운영_상세구현기술서_20260427.md`

## 1. 목적

Phase15의 FastAPI + React/Vite MVP는 PDF 업로드, CLI 실행, 상태 조회, 결과 다운로드, QA 확인까지 기본 흐름을 제공한다.

Step6의 목적은 MVP를 실제 반복 운영 가능한 로컬 업무 도구로 안정화하는 것이다. 핵심은 사용자가 화면에서 선택한 옵션과 실제 CLI/Pipeline 동작을 일치시키고, 실행 결과를 재시작 후에도 추적 가능하게 만들며, 긴 PDF와 장시간 작업에서 로컬 환경이 무너지지 않게 하는 것이다.

우선순위는 다음과 같다.

1. 사용자가 선택한 옵션과 실제 CLI/Pipeline 동작 일치
2. 실행 결과의 추적성 강화
3. Job 운영 안정성 강화
4. UI 사용성 개선
5. 회귀 검증과 기준선 잠금 준비

## 2. 현재 구현 상태 요약

현재 Phase15 MVP의 주요 구현은 다음과 같다.

- `api/app.py`: FastAPI app, `/api/config`, `/api/jobs`, job 조회, 취소, artifact, QA endpoint
- `api/jobs.py`: in-memory `JobManager`, 업로드 저장, CLI subprocess 실행, analyzer 실행, 로그 tail 조회
- `api/artifacts.py`: artifact 목록, 다운로드 경로 방어, QA report 파싱
- `api/schemas.py`: API request/response schema
- `frontend/src/*`: React/Vite 기반 업로드, 상태, 결과, QA, 로그, 매니페스트 UI
- `scripts/frontend_local.ps1`: Google Drive npm 설치 문제를 우회하기 위한 로컬 작업 폴더 빌드 스크립트

현재 확인된 구조상 제약은 다음과 같다.

- `Preset`은 `auto | bom | estimate | pumsem`만 지원한다.
- `generic/범용`은 자동 라우팅의 fallback 결과로만 존재하며 사용자가 강제 선택할 수 없다.
- `OCR 엔진=자동`은 CLI에 `--engine`을 넘기지 않는 의미이며 실제로는 `DEFAULT_ENGINE`을 사용한다.
- 자동 BOM 라우팅 시 `BomPipeline`은 필요하면 `BOM_DEFAULT_ENGINE`으로 엔진을 보정한다.
- `--bom-fallback`은 현재 `preset=bom`일 때만 CLI 명령에 붙는다.
- Job 상태는 메모리에만 있어 API 서버 재시작 후 복구되지 않는다.
- `exit_code` 하나에 CLI 종료 코드와 analyzer 종료 코드가 섞일 수 있다.
- 업로드 파일 크기, 동시 실행, 대기열 제한, 페이지 범위 사전 검증이 부족하다.

## 3. 구현 대상

주요 수정 대상:

```text
api/schemas.py
api/app.py
api/jobs.py
api/artifacts.py
cli/args.py
pipelines/document_pipeline.py
frontend/src/api/client.ts
frontend/src/labels.ts
frontend/src/App.tsx
frontend/src/components/UploadPanel.tsx
frontend/src/components/JobStatusPanel.tsx
frontend/src/components/ArtifactList.tsx
frontend/src/components/QASummary.tsx
frontend/src/components/LogViewer.tsx
frontend/src/components/ManifestViewer.tsx
tests/unit/api/
tests/unit/cli/test_args.py
tests/unit/pipelines/test_document_pipeline.py
```

필요 시 추가 파일:

```text
api/state.py
api/validation.py
frontend/src/utils/validation.ts
```

새 산출물:

```text
output/ui_runs/<job_id>/JOB_STATUS.json
```

## 4. 제외 범위

이번 Step6에서 제외하는 항목은 다음과 같다.

- 원격 배포
- 사용자 인증
- DB 도입
- WebSocket 실시간 로그
- 다중 파일 batch UI
- Excel 웹 미리보기
- OCR/Pipeline 핵심 알고리즘 재설계
- Gemini/Z.ai API key 관리 UI
- 외부 큐 또는 worker process 도입

## 5. 개선 항목 1: 문서 유형 `범용` 명시 옵션 추가

### 5.1 문제

현재 `generic/범용`은 자동 판별 결과가 특화 문서로 확정되지 않을 때 들어가는 내부 fallback 경로다. 사용자는 “자동 판별하지 말고 일반 문서로 처리”를 화면에서 명시할 수 없다.

이 상태에서는 다음 요구를 만족하지 못한다.

- 견적서나 BOM처럼 보이지만 일반 문서로 처리하고 싶음
- 자동 라우팅 실험 없이 안정적인 generic 산출물을 만들고 싶음
- `_compare/.../generic` 진단본이 아니라 대표 산출물 자체를 generic으로 만들고 싶음

### 5.2 정책

`generic`을 정식 preset으로 승격한다.

변경 후 preset은 다음과 같다.

```text
auto
generic
bom
estimate
pumsem
```

표시명은 다음과 같다.

```text
auto     -> 자동
generic  -> 범용
bom      -> BOM 도면
estimate -> 견적서
pumsem   -> 품셈
```

### 5.3 API/CLI 변경

`api/schemas.py`:

```text
Preset = Literal["auto", "generic", "bom", "estimate", "pumsem"]
PRESETS = ("auto", "generic", "bom", "estimate", "pumsem")
```

`cli/args.py`:

```text
--preset choices = ["generic", "pumsem", "estimate", "bom"]
```

`api/jobs.py`:

```text
preset=generic -> --preset generic
```

### 5.4 Pipeline 변경

`DocumentPipeline`은 `preset=generic`을 받으면 자동 라우팅을 건너뛴다.

처리 규칙:

```text
explicit_preset == "generic"
-> preset_data는 빈 값 사용
-> _analyze_routing 호출하지 않음
-> _export_generic_bundle 호출
-> manifest domain은 generic
-> role은 representative
```

`generic`은 `estimate`, `pumsem`처럼 preset data를 로드하지 않는다.

### 5.5 UI 변경

문서 유형 드롭다운:

```text
자동
범용
BOM 도면
견적서
품셈
```

`범용` 선택 시:

- BOM 보조 산출물 옵션 비활성화
- 설명 문구: `자동 판별 없이 일반 문서 경로로 처리합니다.`
- 결과 탭의 문서 영역은 `일반`으로 표시

### 5.6 완료 기준

- `문서 유형=범용` 실행 시 CLI command에 `--preset generic`이 포함된다.
- BOM/견적서/품셈으로 감지 가능한 입력이어도 특화 라우팅이 실행되지 않는다.
- 생성된 대표 산출물의 domain은 `generic`이다.
- UI 결과 탭에서 `일반`으로 표시된다.

## 6. 개선 항목 2: 자동 문서 유형에서 BOM 보조 산출물 옵션 전달

### 6.1 문제

현재 `--bom-fallback`은 `preset=bom`일 때만 CLI 명령에 전달된다. 하지만 `preset=auto`에서도 자동 라우팅 결과 BOM이 선택될 수 있다.

따라서 사용자가 다음처럼 선택하면 기대와 실제 동작이 어긋날 수 있다.

```text
문서 유형: 자동
BOM 보조 산출물: 생성 안 함
```

현재 구조에서는 `preset=auto`이므로 `--bom-fallback never`가 CLI에 전달되지 않는다.

### 6.2 정책

`bom_fallback`은 `preset=bom`뿐 아니라 `preset=auto`에서도 의미가 있다.

전달 규칙:

```text
preset=bom  -> --bom-fallback <auto|always|never> 항상 전달
preset=auto -> bom_fallback이 auto가 아니면 --bom-fallback <always|never> 전달
preset=generic|estimate|pumsem -> 전달하지 않음
```

### 6.3 UI 표시 규칙

문서 유형별 BOM 보조 산출물 표시:

```text
auto    -> 활성화
bom     -> 활성화
generic -> 비활성화
estimate -> 비활성화
pumsem -> 비활성화
```

비활성화 시 값은 API 제출 전에 `auto`로 정규화한다.

### 6.4 완료 기준

- `preset=auto`, `bom_fallback=never`는 CLI command에 `--bom-fallback never`를 포함한다.
- `preset=generic`, `bom_fallback=never`는 CLI command에 `--bom-fallback`을 포함하지 않는다.
- 기존 `preset=bom` 동작은 유지된다.

## 7. 개선 항목 3: 요청 엔진과 실제 실행 엔진 분리 표시

### 7.1 문제

현재 UI의 `OCR 엔진=자동`은 사용자가 보기에는 전체 엔진 자동 선택처럼 보일 수 있다. 실제로는 CLI에 `--engine`을 생략하고 `DEFAULT_ENGINE`을 사용하는 정책이다.

또한 자동 라우팅으로 BOM 특화 경로에 들어가면 `BOM_DEFAULT_ENGINE`으로 보정될 수 있다.

### 7.2 정책

UI와 API 응답에서 다음 개념을 분리한다.

```text
requested_engine: 사용자가 요청한 엔진
effective_engine: 실제 대표 실행 경로에서 사용된 엔진
effective_preset: 실제 대표 실행 경로에서 확정된 문서 유형
```

v1에서 `effective_engine`을 완전하게 얻기 어렵다면 다음 단계로 나눈다.

1. Job status에는 요청값과 기본 설정 힌트를 제공한다.
2. Pipeline/manifest 개선 후 실제 실행 엔진을 기록한다.
3. UI는 실제값이 없으면 `자동(DEFAULT_ENGINE 기준)`처럼 표시한다.

### 7.3 API 변경

`JobStatusResponse`에 추가:

```text
requested_engine: string
effective_engine: string | null
effective_preset: string | null
engine_note: string | null
```

호환을 위해 기존 `engine`은 유지하되 `requested_engine`과 같은 값으로 둔다.

### 7.4 상태 표시 예시

```text
요청 엔진: 자동
기본 엔진: gemini
BOM 특화 기본 엔진: zai
실제 엔진: 결과 확정 후 표시
```

### 7.5 완료 기준

- 사용자는 `자동`이 어떤 기본값을 의미하는지 알 수 있다.
- BOM 자동 라우팅에서 `zai` 전환 가능성이 UI에 드러난다.
- 향후 manifest에 실제 엔진이 기록되면 UI가 그 값을 우선 표시할 수 있다.

## 8. 개선 항목 4: Job 상태 파일 저장

### 8.1 문제

현재 Job 상태는 메모리에만 있다. API 서버를 재시작하면 이미 생성된 `output/ui_runs/<job_id>/` 산출물이 있어도 UI에서 다시 조회할 수 없다.

### 8.2 저장 파일

각 job 폴더에 다음 파일을 저장한다.

```text
output/ui_runs/<job_id>/JOB_STATUS.json
```

필드:

```json
{
  "job_id": "ui_20260427_143012_a1b2c3d4",
  "status": "succeeded",
  "preset": "auto",
  "engine": "auto",
  "requested_engine": "auto",
  "effective_engine": null,
  "effective_preset": null,
  "pages": "1-10",
  "bom_fallback": "never",
  "no_cache": false,
  "input_path": "input/sample.pdf",
  "result_dir": "result",
  "stdout_log": "logs/stdout.log",
  "stderr_log": "logs/stderr.log",
  "command": ["python", "main.py", "..."],
  "created_at": "2026-04-27T14:30:12+09:00",
  "started_at": "2026-04-27T14:30:13+09:00",
  "finished_at": "2026-04-27T14:31:20+09:00",
  "cli_exit_code": 0,
  "analyzer_exit_code": 0,
  "exit_code": 0,
  "message": "작업이 완료되었습니다."
}
```

주의:

- 절대 경로 대신 job 폴더 기준 상대 경로를 저장한다.
- `.env`, API key, 환경변수 값은 저장하지 않는다.
- command에는 입력 파일 경로와 옵션만 저장하고 secret은 포함하지 않는다.

### 8.3 API 변경

신규 endpoint:

```text
GET /api/jobs
```

동작:

- `output/ui_runs/*/JOB_STATUS.json`을 읽는다.
- `created_at desc`로 정렬한다.
- 기본 반환 개수는 50개다.
- 깨진 상태 파일은 건너뛰고 서버 로그 또는 응답 message에 경고를 남긴다.

기존 endpoint:

```text
GET /api/jobs/{job_id}
```

동작 변경:

- 메모리에 없으면 `JOB_STATUS.json`에서 복구를 시도한다.
- 복구된 job은 산출물/QA 조회에 사용할 수 있다.
- `running`으로 남아 있으나 process가 없으면 `failed` 또는 `unknown` 복구 상태로 표시한다.

### 8.4 완료 기준

- API 서버 재시작 후에도 완료된 job을 조회할 수 있다.
- UI에서 최근 작업 목록을 표시하고 선택할 수 있다.
- 상태 파일에 secret이 포함되지 않는다.

## 9. 개선 항목 5: CLI 종료 코드와 QA Analyzer 종료 코드 분리

### 9.1 문제

현재 `exit_code` 하나가 CLI 종료 코드였다가 analyzer 종료 코드로 덮일 수 있다. 그러면 실패가 CLI 단계인지 QA 분석 단계인지 바로 알기 어렵다.

### 9.2 정책

종료 코드를 세 개로 분리한다.

```text
cli_exit_code: main.py 실행 종료 코드
analyzer_exit_code: tools/analyze_outputs.py 종료 코드
exit_code: 최종 호환 필드
```

`exit_code` 호환 규칙:

```text
CLI 실패 -> cli_exit_code
CLI 성공 + analyzer 실패 -> analyzer_exit_code
둘 다 성공 -> 0
취소 -> null 또는 프로세스 종료 코드
```

### 9.3 UI 변경

상태 패널 표시:

```text
CLI 종료 코드
QA 종료 코드
최종 상태
```

실패 메시지:

```text
CLI 실행이 실패했습니다. cli_exit_code=1
QA 분석 단계에서 실패했습니다. analyzer_exit_code=1
```

### 9.4 완료 기준

- CLI 실패와 QA 실패를 UI에서 구분할 수 있다.
- API 테스트에서 두 종료 코드가 별도로 검증된다.
- 기존 `exit_code` 필드는 즉시 제거하지 않는다.

## 10. 개선 항목 6: 업로드/실행 안정성 제한

### 10.1 문제

긴 PDF, 대량 업로드, 동시 실행은 로컬 환경과 Google Drive 동기화 환경을 불안정하게 만들 수 있다.

현재 부족한 제한:

- 업로드 파일 크기 제한
- 동시 실행 제한
- 대기열 제한
- 페이지 범위 API 사전 검증

### 10.2 설정값

환경변수:

```text
UI_MAX_UPLOAD_MB=200
UI_MAX_CONCURRENT_JOBS=1
UI_MAX_QUEUED_JOBS=10
```

기본값:

```text
max upload: 200MB
max concurrent jobs: 1
max queued jobs: 10
```

### 10.3 API 검증

업로드 검증:

```text
빈 파일 -> invalid_upload
PDF 아님 -> invalid_upload
크기 초과 -> upload_too_large
```

실행 제한:

```text
running job 수 >= UI_MAX_CONCURRENT_JOBS -> too_many_running_jobs
queued job 수 >= UI_MAX_QUEUED_JOBS -> queue_full
```

페이지 범위 검증:

```text
허용: 1, 1-10, 20-, 1,3,5-10
거부: 0, -1, a-b, 5-3, 1,,2
```

페이지 총수 기반 검증은 기존 CLI 단계에서 수행하고, API는 형식 검증까지만 담당한다.

### 10.4 완료 기준

- 제한 초과는 structured error로 응답한다.
- UI는 한글 오류 메시지를 표시한다.
- 테스트에서 파일 크기, 동시 실행, 큐 제한, 페이지 형식 오류를 재현한다.

## 11. 개선 항목 7: UI 사용성 개선

### 11.1 옵션 설명

문서 유형별 설명:

```text
자동: 문서 내용을 분석해 특화 또는 범용 경로로 처리합니다.
범용: 자동 판별 없이 일반 문서 경로로 처리합니다.
BOM 도면: BOM 전용 추출/표 정합성 경로로 처리합니다.
견적서: 견적서 preset 기준으로 처리합니다.
품셈: 품셈 preset 기준으로 처리합니다.
```

OCR 엔진 자동 설명:

```text
자동은 전체 엔진을 비교한다는 뜻이 아니라 기본 엔진 설정을 사용한다는 뜻입니다.
```

### 11.2 조건부 옵션

BOM 보조 산출물:

```text
auto 또는 bom -> 활성화
generic, estimate, pumsem -> 비활성화
```

캐시 미사용:

```text
항상 표시하되, 긴 PDF에서는 실행 시간이 길어질 수 있음을 안내
```

### 11.3 결과 탭 개선

결과 목록은 role 기준으로 그룹화한다.

```text
대표 산출물
진단 산출물
기타 산출물
```

각 행 표시:

```text
파일명
상대 경로
종류
문서 영역
역할
품질
크기
다운로드
```

### 11.4 QA 탭 개선

`WARN`일 때 원인을 먼저 보여준다.

우선 표시:

```text
품질 주의 항목
Header/key mismatch
Bad composite headers
Manifest domain count
```

### 11.5 로그 탭 개선

stdout/stderr를 구분한다.

```text
stdout tail
stderr tail
```

v1은 기존 `log_tail`을 유지하되, API 응답 확장 시 다음 구조를 추가한다.

```text
stdout_tail: string[]
stderr_tail: string[]
```

### 11.6 매니페스트 탭 개선

원문 markdown만 표시하지 않고 요약 표를 먼저 보여준다.

표시 순서:

1. 대표 산출물 요약
2. 진단 산출물 요약
3. domain/quality count
4. 원문 `RUN_SUMMARY.md` 또는 `OUTPUT_QA_REPORT.md`

## 12. API Interface 변경 명세

### 12.1 ConfigResponse

```json
{
  "presets": ["auto", "generic", "bom", "estimate", "pumsem"],
  "engines": ["auto", "zai", "gemini", "local", "mistral", "tesseract"],
  "bom_fallback_modes": ["auto", "always", "never"],
  "defaults": {
    "preset": "auto",
    "engine": "auto",
    "output_format": "excel",
    "bom_fallback": "auto"
  }
}
```

### 12.2 JobStatusResponse

추가 필드:

```json
{
  "cli_exit_code": 0,
  "analyzer_exit_code": 0,
  "effective_preset": "generic",
  "effective_engine": "gemini",
  "engine_note": "engine=auto는 DEFAULT_ENGINE 기준으로 실행됩니다.",
  "stdout_tail": [],
  "stderr_tail": []
}
```

기존 필드:

```text
exit_code
log_tail
```

기존 필드는 호환을 위해 유지한다.

### 12.3 Jobs List Response

```json
{
  "jobs": [
    {
      "job_id": "ui_20260427_143012_a1b2c3d4",
      "status": "succeeded",
      "preset": "auto",
      "engine": "auto",
      "created_at": "2026-04-27T14:30:12+09:00",
      "finished_at": "2026-04-27T14:31:20+09:00",
      "message": "작업이 완료되었습니다."
    }
  ]
}
```

## 13. 구현 순서

구현은 아래 순서로 진행한다.

1. API/CLI preset contract 확장
   - `generic` 추가
   - 관련 테스트 추가
2. `DocumentPipeline` generic 강제 경로 구현
   - 자동 라우팅 skip
   - representative generic 산출물 검증
3. BOM fallback 전달 규칙 수정
   - `preset=auto` + `bom_fallback != auto` 처리
4. 종료 코드 분리
   - `cli_exit_code`, `analyzer_exit_code` 추가
5. `JOB_STATUS.json` 저장/복구
   - status write/read
   - `GET /api/jobs` 추가
6. 업로드/실행 제한 추가
   - 파일 크기
   - 동시 실행
   - 대기열
   - 페이지 형식
7. 프론트 타입/API/UI 반영
   - `generic` 표시
   - 조건부 옵션
   - 상태/결과/QA 표시 개선
8. focused test 및 build
9. 실측 PDF smoke
10. 결과 보고서 작성

## 14. 테스트 계획

### 14.1 API unit

명령:

```powershell
python -m pytest --no-cov tests/unit/api
```

추가 테스트:

- `/api/config`에 `generic` 포함
- `preset=generic` command에 `--preset generic` 포함
- `preset=auto`, `bom_fallback=never` command에 `--bom-fallback never` 포함
- `preset=estimate`, `bom_fallback=never` command에는 `--bom-fallback` 미포함
- 파일 크기 초과 오류
- 잘못된 페이지 범위 오류
- 동시 실행 제한 오류
- `JOB_STATUS.json` 저장/복구
- CLI/analyzer exit code 분리

### 14.2 CLI/Pipeline unit

명령:

```powershell
python -m pytest --no-cov tests/unit/cli/test_args.py tests/unit/pipelines/test_document_pipeline.py tests/unit/pipelines/test_bom_pipeline.py
```

검증:

- `--preset generic` 파싱
- `generic`은 자동 라우팅을 건너뜀
- `auto`는 기존 자동 라우팅 유지
- BOM auto-route에서 `BOM_DEFAULT_ENGINE` 보정 유지

### 14.3 Frontend build

명령:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\frontend_local.ps1 build
```

검증:

- TypeScript compile 통과
- `generic` 타입/라벨 반영
- 조건부 BOM fallback UI compile 통과

### 14.4 Integration / smoke

시나리오:

- PDF 업로드 -> 자동 -> 성공 -> 산출물/QA 조회
- PDF 업로드 -> 범용 -> 특화 라우팅 없이 generic 결과 생성
- BOM PDF 업로드 -> 자동 + fallback never -> diagnostic 생성 정책 확인
- API 서버 재시작 후 기존 job 조회
- 실측 샘플 `53-83 OKOK.pdf`는 페이지 범위 `1-10` 우선 검증

### 14.5 Regression

최종 잠금 전 명령:

```powershell
python -m pytest
git diff --check
```

## 15. 완료 기준

Step6은 다음 조건을 모두 만족하면 완료로 본다.

- `generic/범용`을 사용자가 직접 선택할 수 있다.
- `preset=generic`은 자동 라우팅을 수행하지 않는다.
- `preset=auto`에서도 BOM fallback 정책이 CLI/Pipeline에 전달된다.
- 요청 엔진과 실제 적용 기준을 UI에서 구분할 수 있다.
- API 재시작 후 완료된 job을 다시 조회할 수 있다.
- CLI 실패와 QA analyzer 실패를 구분할 수 있다.
- 업로드 크기, 동시 실행, 큐, 페이지 형식 제한이 동작한다.
- 프론트 빌드와 API focused tests가 통과한다.
- 실측 PDF smoke 결과를 보고서에 남긴다.

## 16. 남은 위험

- 현재 워크트리에는 Phase15뿐 아니라 백엔드 안정화 변경이 함께 섞여 있다. Step6 구현 전후 커밋 단위 분리가 필요하다.
- `generic`을 정식 preset으로 추가하면 CLI/Pipeline contract가 바뀌므로 전체 회귀 테스트가 필요하다.
- `effective_engine`은 현재 manifest에 완전히 기록되지 않을 수 있다. v1은 기본 설정 힌트를 먼저 표시하고, 실제 엔진 기록은 후속 보강으로 나눌 수 있다.
- Google Drive 경로에서 npm 대량 쓰기는 여전히 위험하다. 프론트 검증은 `scripts/frontend_local.ps1`을 표준으로 유지한다.
- `.env`는 열람하지 않으며, 상태 파일과 로그에 secret이 남지 않는지 파일 목록과 샘플 내용 기준으로 확인해야 한다.

## 17. 결과 보고서 작성 기준

구현 후 다음 파일에 결과를 기록한다.

```text
Project/PJT_A/04_Phase별_결과보고서/Phase15-Step6_UI_API운영안정화_구현결과보고서_20260427.md
```

보고서에는 다음을 포함한다.

- 구현 요약
- 변경 파일 목록
- API/CLI/UI contract 변경
- 실행한 테스트 명령과 결과
- 실측 PDF smoke 결과
- 남은 위험
- 다음 작업 권장 순서
