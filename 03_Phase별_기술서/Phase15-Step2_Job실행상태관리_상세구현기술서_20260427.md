# Phase15-Step2 Job 실행 상태 관리 상세 구현 기술서

작성일: 2026-04-27

대상 프로젝트: `Project/PJT_A/ps-docparser`

## 1. 목적

업로드된 PDF를 기존 CLI로 실행하고, 실행 상태를 API와 UI에서 조회할 수 있게 한다.

Step2의 핵심은 `job_id`, 작업 폴더, subprocess, 상태 전이, 로그, 취소 처리다.

## 2. 구현 대상

주요 파일:

```text
api/jobs.py
api/schemas.py
api/app.py
tests/unit/api/test_jobs.py
```

작업 폴더:

```text
output/ui_runs/<job_id>/
  input/
    uploaded.pdf
  result/
  logs/
    stdout.log
    stderr.log
```

## 3. 제외 범위

- DB job 저장
- 여러 프로세스 간 job 공유
- WebSocket push
- job retry
- 예약 실행
- remote worker

## 4. Job 상태 모델

상태:

```text
queued
running
succeeded
failed
canceled
```

상태 전이:

```text
queued -> running -> succeeded
queued -> running -> failed
queued -> running -> canceled
queued -> canceled
```

금지 전이:

```text
succeeded -> running
failed -> running
canceled -> running
```

## 5. JobRecord 필드

내부 record:

```text
job_id: string
input_path: Path
result_dir: Path
stdout_log: Path
stderr_log: Path
preset: string
engine: string
pages: string | None
bom_fallback: string
no_cache: bool
status: JobStatus
created_at: datetime
started_at: datetime | None
finished_at: datetime | None
exit_code: int | None
process: subprocess.Popen | None
message: string | None
```

v1 registry:

```text
dict[str, JobRecord]
```

## 6. job_id 생성

형식:

```text
ui_YYYYMMDD_HHMMSS_<8hex>
```

예:

```text
ui_20260427_143012_a1b2c3d4
```

규칙:

- 파일 경로에 안전한 문자만 사용
- 중복 시 재생성
- job_id는 사용자 입력에서 받지 않음

## 7. CLI subprocess 명령 생성

기본 명령:

```powershell
python main.py <input_path> --engine <engine> --output-dir <result_dir> --output excel
```

engine 처리:

```text
engine=auto -> --engine 생략
그 외 engine -> --engine <engine>
```

preset 처리:

```text
preset=auto      -> --preset 생략
preset=bom       -> --preset bom
preset=estimate  -> --preset estimate
preset=pumsem    -> --preset pumsem
```

pages 처리:

```text
pages 값 있음 -> --pages <pages>
pages 값 없음 -> 생략
```

BOM fallback 처리:

```text
preset=bom -> --bom-fallback <auto|always|never>
그 외 preset -> 생략
```

cache 처리:

```text
no_cache=true -> --no-cache
no_cache=false -> 생략
```

## 8. 실행 흐름

1. `POST /api/jobs`가 업로드 파일을 저장한다.
2. JobRecord를 만들고 registry에 등록한다.
3. background task 또는 thread executor가 실행을 시작한다.
4. 상태를 `running`으로 바꾼다.
5. stdout/stderr를 로그 파일로 연결해 subprocess를 실행한다.
6. CLI 종료 코드를 받는다.
7. 성공이면 `tools/analyze_outputs.py <result_dir>`를 실행한다.
8. analyzer까지 성공하면 `succeeded`.
9. CLI 또는 analyzer 실패면 `failed`.
10. 종료 시 `finished_at`, `exit_code`, `message`를 기록한다.

## 9. 취소 처리

Endpoint:

```text
POST /api/jobs/{job_id}/cancel
```

규칙:

- `queued`는 바로 `canceled`
- `running`은 subprocess terminate
- terminate 후 timeout이면 kill
- 이미 `succeeded`, `failed`, `canceled`면 현재 상태 반환

취소 메시지:

```text
사용자 요청으로 작업이 취소되었습니다.
```

## 10. 로그 처리

로그 파일:

```text
logs/stdout.log
logs/stderr.log
```

API 응답:

- 마지막 100줄만 반환
- UTF-8 decode 실패 시 replacement 사용
- secret masking filter는 기존 백엔드 설정을 신뢰하되, API에서도 `.env` 내용은 읽지 않음

## 11. 실패/예외 처리

- 업로드 저장 실패: job 생성 전 `500 internal_error`
- subprocess 생성 실패: `failed`
- CLI exit code non-zero: `failed`
- analyzer 실패: `failed`, 단 CLI 산출물은 보존
- cancel timeout: `failed` 또는 `canceled` 중 실제 process 상태 기준으로 기록
- 서버 재시작 시 in-memory job은 사라질 수 있음. v1에서는 허용한다.

## 12. 테스트 계획

- job id 형식 검증
- 명령 생성 snapshot 테스트
- `preset=auto`에서 `--preset` 생략
- `preset=bom`에서 `--bom-fallback` 포함
- `pages` 전달 검증
- 성공 subprocess mock으로 `succeeded`
- 실패 subprocess mock으로 `failed`
- cancel 호출 시 `canceled`
- log tail 반환

## 13. 완료 기준

- 업로드된 PDF가 job 폴더에 저장됨
- subprocess 명령이 기존 CLI 규칙과 일치
- job 상태 조회 가능
- 성공/실패/취소 상태가 구분됨
- 로그 tail 조회 가능
- analyzer가 성공 job 후 자동 실행됨
