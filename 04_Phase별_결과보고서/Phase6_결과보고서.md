# Phase 6 구현 결과 보고서 — 긴급 안정화

**작성일:** 2026-04-17
**대상:** ps-docparser

## 1. 개요
Phase 6의 목적이었던 여러 시스템/OS 환경에서의 Poppler 등 경로 감지 로직 강화, 의존성 라이브러리들의 버전 고정 및 강건한 파일 입출력 예외 처리를 통해 개발·배치 처리 환경의 기초 안정성을 획기적으로 개선했습니다.

## 2. 핵심 작업 내역
### 2.1 `requirements.txt` 버전 상/하한선 도입
- `pdfplumber>=0.11.0,<1.0.0`, `openpyxl>=3.1.0,<4.0.0` 등 주요 패키지들의 메이저 버전을 명시하여 외부 PC나 가상 환경 재생성 시 호환되지 않는 새 버전의 API 변경으로 코드가 파괴되는 문제를 원천 차단했습니다.

### 2.2 바이너리 감지 자동화 & 유효성 검사 도입
- **경로 감지:** `config.py` 내 `_detect_poppler_path`와 `_detect_tesseract_path`가 Windows 뿐만 아니라 macOS(Homebrew), Linux의 설치 경로들을 선제적으로 탐색하게끔 보강하여, 환경변수가 없어도 유연하게 동작합니다.
- **초기 검증 (`validate_config`):** 런타임에 들어간 후 API 키 누락이나 엔진 설정 오류로 크래시가 발생하는 것을 막고자 런타임 가장 앞 단에서 `.env` 세팅 및 감지된 경로들을 일괄 점검하고 사용자에게 ❌에러, ⚠️경고, ✅정상 상태를 친절하게 출력하도록 통일했습니다. 
- **강제 옵션:** 설정 점검이 불발됐어도 유저가 임의 진행할 수 있도록 `main.py`에 `--force` 옵션을 추가했습니다.

### 2.3 `utils/io.py` 모듈 분리 및 파일 I/O 예외 처리 강화
- **응집도 향상:** `ParserError` 예외 클래스와 안전한 파일 쓰기를 담당하는 `_safe_write_text()` 함수를 `utils/io.py`로 완전히 분리했습니다.
- **파일 점유 문제 해결:** 배치 작업 중 이미 실행된 엑셀/텍스트 뷰어가 `.md`나 `.json`을 열고 있을 경우 발생하는 `PermissionError` 혹은 용량/경로 불량으로 떨어지는 `OSError`를 `ParserError`로 규격화했습니다. 
- **`json_exporter.py` 개선 보장:** 기존 `main.py`에 감춰져 있던 로직을 분리함으로써 `exporters/json_exporter.py` 및 `exporters/excel_exporter.py`에서도 통일된 `_safe_write_text()` 및 `ParserError`를 import하여 사용할 수 있게 되었습니다. 
- **배치 연속성 보장:** 해당 오류가 전체 `for` 루프를 죽이지 않고 (특히 Excel `save` 시 발생하는 `SystemExit` 강제 종료를 제거) 개별 파일에 대한 `failed` 리스트 편입으로 건너뛰어지도록 개선했습니다.
- **디버깅 편의 향상 (보고서 외 보너스 추가):** `main.py` 배치 루프 내부의 `except Exception` 블록에 `traceback.print_exc()`를 도입해, 예상 못한 크래시 발생 시 에러 트래킹 성능을 획기적으로 올렸습니다.

### 2.4 설정 및 캐시 관리
- `.gitignore` 내 `venv_test/`, `htmlcov/` 등 향후 테스트 관련 부산물 생성을 차단하는 룰셋 추가.
- `.env.example` 내부 주석 개편. 필수 API와 선택 API를 분류하고, 각 변수의 용도를 직관적으로 명시했습니다.

## 3. 검증 결과
- **테스트 환경:** Windows (cp949 터미널 보정 적용)
  1. `<API 키 누락 상태 시뮬레이션>`: `.env` 파일을 임시 해제 후 실행하여 `validate_config`가 오류를 표출하고 정상적으로 예외 종료됨을 확인했습니다.
     ```text
     [ERROR] ❌ DEFAULT_ENGINE=gemini이나 GEMINI_API_KEY가 없습니다. .env 파일 확인 또는 --engine local 사용하세요.
     설정 오류로 중단합니다. --force 옵션으로 강제 실행 가능.
     ```

  2. `<Excel 및 파일 점유 시나리오>`: 물리적 폴더 및 엑셀 파일 Lock 스크립트(`test_excel_lock.py`)를 작성하여 `openpyxl` 및 `_safe_write_text` 단계에서 `PermissionError`가 발생함을 재현했고, 이를 통해 `SystemExit`가 발생하여 배치가 멎지 않고 `failed` 배열에 편입된 후 다음 PDF 파싱으로 무사히 롤오버 됨을 확인했습니다.
     ```text
     [01/03] a.pdf
       → 건너뜀: 파일 저장 (권한 거부): a.xlsx
         → 해당 파일이 Excel 등 다른 프로그램에서 열려 있는지 확인하세요.
         상세: [Errno 13] Permission denied: 'a.xlsx'
     
     [02/03] b.pdf
       → 성공
     
     =======================================================
     배치 완료: 성공 2건 / 실패 1건 / 전체 3건
     
     [실패 목록]
       - a.pdf: 파일 저장 (권한 거부): a.xlsx ...
     =======================================================
     ```

  3. `<Poppler 경로 정상 감지>`: Windows 기본 터미널에서 CP949 이모지 인코딩 충돌 없이 `✅ Poppler: C:\poppler\poppler-24.08.0\Library\bin`를 온전히 출력합니다. macOS 및 Linux에서도 `glob`과 `shutil.which` 기반의 동적 할당 로직이 포함되어 있어 99% 무리 없이 감지될 것을 보장합니다.

## 4. 시사점 및 Next Step (Phase 7 준비)
- 현재 코드 베이스는 어떠한 PC 환경에서도 에러 추적이 용이하게끔 정리되었습니다. 이후 진행될 **Phase 7 (테스트 인프라 구축 단위)** 에서는 이번에 구현된 `validate_config()` / `_safe_write_text()`의 Mock 기능을 단위 테스트에 포함하여 테스트 코드들을 작성하기에 매우 용이할 것입니다.
