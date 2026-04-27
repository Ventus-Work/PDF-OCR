# Phase15-Step4 React/Vite UI 상세 구현 기술서

작성일: 2026-04-27

대상 프로젝트: `Project/PJT_A/ps-docparser`

## 1. 목적

FastAPI API를 사용하는 로컬 웹 UI를 구현한다.

첫 화면은 설명용 랜딩이 아니라 실제 작업 화면이다. 사용자는 PDF를 업로드하고 옵션을 선택한 뒤 실행 결과와 QA를 확인할 수 있어야 한다.

## 2. 구현 대상

신규 폴더:

```text
ps-docparser/frontend/
```

주요 파일:

```text
frontend/package.json
frontend/index.html
frontend/src/main.tsx
frontend/src/App.tsx
frontend/src/api/client.ts
frontend/src/components/UploadPanel.tsx
frontend/src/components/JobStatusPanel.tsx
frontend/src/components/ArtifactList.tsx
frontend/src/components/QASummary.tsx
frontend/src/components/LogViewer.tsx
frontend/src/components/ManifestViewer.tsx
frontend/src/styles.css
```

권장 의존성:

```text
vite
typescript
react
react-dom
```

구현 중 조정 사항:

- Google Drive 동기화 경로에서 `lucide-react` 설치 중 `TAR_ENTRY_ERROR UNKNOWN: unknown error, write`가 반복되었다.
- v1 MVP에서는 npm 설치 안정성을 우선해 `lucide-react` 의존성을 제외한다.
- 버튼과 탭에는 CSS 기반 `icon-mark` 보조 표식을 사용한다.
- 비동기 설치 환경이 안정된 로컬/CI에서는 추후 lucide icon으로 교체할 수 있다.

## 3. 제외 범위

- 마케팅 랜딩 페이지
- 로그인/계정
- 원격 배포
- Excel 미리보기
- JSON 테이블 편집
- drag-and-drop 다중 파일 batch
- WebSocket

## 4. 화면 구조

첫 화면 레이아웃:

```text
Header
Main
  Left: UploadPanel
  Right: JobStatusPanel
Bottom/Full width: ResultTabs
  - 결과
  - QA
  - 로그
  - Manifest
```

디자인 성격:

- 업무 도구형 UI
- 조용하고 밀도 있는 정보 구조
- 카드 남발 금지
- 결과와 상태를 빠르게 스캔할 수 있게 구성
- 버튼에는 가능한 경우 lucide icon 사용

## 5. UploadPanel

입력:

- PDF 파일
- preset
  - auto
  - bom
  - estimate
  - pumsem
- engine
  - auto
  - zai
  - gemini
  - local
  - mistral
  - tesseract
- pages
  - optional text
  - 예: `1-10`, `20-`, `1,3,5-10`
- BOM fallback
  - auto
  - always
  - never
- no cache
  - checkbox

동작:

- PDF가 없으면 실행 버튼 비활성화
- 실행 중에는 입력 잠금
- preset이 `bom`이 아닐 때 fallback 선택은 비활성화
- engine `auto`는 CLI 기본 엔진을 사용한다는 의미로 표시
- 제출 시 `POST /api/jobs`

## 6. JobStatusPanel

표시:

- job id
- 상태 badge
- preset
- engine
- created/started/finished time
- exit code
- message

상태 색상:

- queued: neutral
- running: blue
- succeeded: green
- failed: red
- canceled: gray

동작:

- `queued`, `running` 상태에서 polling
- 기본 polling 간격 2초
- `running` 상태에서 cancel 버튼 표시
- 완료 후 artifact와 QA 자동 조회

## 7. Result Tabs

### 결과 탭

표시:

- representative artifacts
- diagnostic artifacts
- 기타 artifacts

각 행:

- 이름
- 종류
- domain
- role
- quality
- size
- 다운로드 버튼

### QA 탭

표시:

- Status
- JSON files
- Excel files
- RUN_MANIFEST 존재 여부
- Manifest representative
- Manifest diagnostic
- Header/key mismatch
- Bad composite headers
- Quality warnings
- Manifest domains

`WARN`은 실패가 아니라 주의 상태로 표시한다.

### 로그 탭

표시:

- log tail
- stderr가 있으면 접을 수 있는 영역으로 표시
- secret처럼 보이는 값은 표시하지 않는 것을 원칙으로 한다.

### Manifest 탭

표시:

- `RUN_MANIFEST.json` 원문 또는 요약
- representative/diagnostic 구조
- source PDF와 domain/quality

## 8. API client

`frontend/src/api/client.ts` 함수:

```text
getConfig()
createJob(form)
getJob(jobId)
cancelJob(jobId)
getArtifacts(jobId)
getQA(jobId)
downloadArtifact(jobId, artifactId)
```

기본 API base:

```text
http://127.0.0.1:8000
```

개발 중 Vite proxy를 쓰는 경우:

```text
/api -> http://127.0.0.1:8000/api
```

## 9. 상태 관리

v1은 전역 상태 라이브러리를 도입하지 않는다.

상태:

```text
config
selectedFile
formOptions
currentJob
artifacts
qa
logs
activeTab
error
```

React hooks:

- `useState`
- `useEffect`
- `useMemo`

## 10. 실패/예외 UX

- API 연결 실패: 서버 실행 안내
- 업로드 실패: 오류 메시지 표시
- job 실패: failed badge와 log tail 표시
- QA 없음: "QA 리포트가 아직 없습니다" 표시
- 다운로드 실패: artifact 오류 메시지 표시

## 11. 접근성/사용성

- 버튼 텍스트는 짧고 명확하게
- 실행 중 loading 표시
- 긴 파일명은 줄바꿈
- 작은 화면에서도 업로드 패널과 결과 탭이 겹치지 않게 구성
- 모든 icon button에는 title 또는 aria-label

## 12. 테스트 계획

- `npm run build`
- API mock으로 UploadPanel submit 검증
- job polling이 terminal state에서 멈추는지 확인
- QA `WARN` 표시 확인
- artifact download link 생성 확인
- 작은 viewport에서 레이아웃 깨짐 확인

## 13. 완료 기준

- PDF 업로드 가능
- job 실행 가능
- 상태 polling 가능
- 결과 목록 표시
- QA 요약 표시
- md/json/xlsx 다운로드 가능
- `npm run build` 통과
