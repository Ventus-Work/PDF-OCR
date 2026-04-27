# Phase15-Step1 FastAPI API 어댑터 상세 구현 기술서

작성일: 2026-04-27

대상 프로젝트: `Project/PJT_A/ps-docparser`

## 1. 목적

기존 CLI 기반 `ps-docparser`를 프론트엔드에서 호출할 수 있도록 로컬 HTTP API를 추가한다.

Step1의 목표는 API 계약과 서버 구조를 고정하는 것이다. 실제 장시간 실행, artifact 세부 탐색, React UI는 후속 Step에서 다룬다.

## 2. 구현 대상

신규 폴더:

```text
ps-docparser/api/
```

신규 파일:

```text
api/__init__.py
api/app.py
api/schemas.py
api/jobs.py
api/artifacts.py
```

수정 파일:

```text
requirements.txt
README.md
```

의존성:

```text
fastapi
uvicorn
python-multipart
```

## 3. 제외 범위

Step1에서는 다음을 구현하지 않는다.

- React/Vite UI
- DB 영속화
- 사용자 인증
- WebSocket
- 원격 배포
- 파서 pipeline 직접 호출

## 4. API endpoint 계약

Phase15 v1 endpoint는 아래로 고정한다.

```text
GET  /api/config
POST /api/jobs
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/{job_id}/artifacts
GET  /api/jobs/{job_id}/artifacts/{artifact_id}
GET  /api/jobs/{job_id}/qa
```

Step1에서 최소 구현:

- `GET /api/config`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`

나머지는 stub 또는 명확한 `501 Not Implemented`로 둘 수 있다. 단 endpoint 이름과 응답 형식은 고정한다.

## 5. schemas.py 설계

핵심 타입:

```text
Preset = auto | bom | estimate | pumsem
Engine = auto | zai | gemini | local | mistral | tesseract
BomFallback = auto | always | never
JobStatus = queued | running | succeeded | failed | canceled
```

응답 모델:

```text
ConfigResponse
CreateJobResponse
JobStatusResponse
ArtifactItem
ArtifactsResponse
QAResponse
ErrorResponse
```

`ConfigResponse` 필드:

```text
presets: string[]
engines: string[]
bom_fallback_modes: string[]
defaults:
  preset: auto
  engine: auto
  output_format: excel
  bom_fallback: auto
```

`CreateJobResponse` 필드:

```text
job_id: string
status: queued | running
status_url: string
```

`JobStatusResponse` 필드:

```text
job_id: string
status: JobStatus
preset: string
engine: string
created_at: string
started_at: string | null
finished_at: string | null
exit_code: int | null
message: string | null
log_tail: string[]
```

## 6. app.py 설계

역할:

- FastAPI app 생성
- router 등록
- CORS 설정
- static frontend serving은 v1에서 선택 사항으로 둠

기본 실행:

```powershell
uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
```

서버 기본 정책:

- host 기본값은 `127.0.0.1`
- CORS는 개발 중 `http://localhost:5173`만 허용
- 응답은 JSON
- 예외는 `ErrorResponse` 구조로 통일

## 7. POST /api/jobs 입력

multipart form:

```text
file: PDF
preset: auto | bom | estimate | pumsem
engine: auto | zai | gemini | local | mistral | tesseract
pages: string | null
bom_fallback: auto | always | never
no_cache: bool
```

검증:

- 파일 확장자는 `.pdf`
- 빈 파일 거부
- `pages`는 빈 문자열이면 None 처리
- `preset=auto`면 CLI에 `--preset`을 넣지 않음
- `engine=auto`면 CLI에 `--engine`을 넣지 않고 기존 config 기본 엔진을 사용함
- `preset=bom`일 때만 `bom_fallback` 의미가 있음

## 8. 에러 응답

공통 구조:

```json
{
  "error": {
    "code": "invalid_upload",
    "message": "PDF 파일만 업로드할 수 있습니다.",
    "details": {}
  }
}
```

주요 코드:

```text
invalid_upload
invalid_option
job_not_found
job_not_running
artifact_not_found
unsafe_path
internal_error
```

## 9. 보안 규칙

- 업로드 파일명은 원본 그대로 저장하지 않고 sanitize한다.
- job 디렉토리는 `output/ui_runs/<job_id>/` 아래만 사용한다.
- API 응답에 `.env`, API key, absolute secret path를 노출하지 않는다.
- log tail은 마지막 N줄만 반환한다.
- 다운로드 path traversal은 Step3에서 강제한다.

## 10. 테스트 계획

API unit tests:

- `GET /api/config`가 모든 option을 반환
- PDF가 아닌 파일은 `400 invalid_upload`
- `POST /api/jobs`가 job id를 반환
- 생성된 job status가 `queued` 또는 `running`
- 없는 job 조회는 `404 job_not_found`
- `preset=auto` 요청이 내부 job option에 auto로 저장됨
- `preset=bom` 요청에서 fallback option이 저장됨

## 11. 완료 기준

- FastAPI 서버가 로컬에서 실행됨
- `GET /api/config` 정상 응답
- `POST /api/jobs`로 job id 생성
- `GET /api/jobs/{job_id}`로 상태 조회
- API focused tests 통과
- 기존 `pytest` 회귀 통과
