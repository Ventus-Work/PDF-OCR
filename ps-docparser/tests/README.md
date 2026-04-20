# ps-docparser Test Suite

이 디렉토리는 `ps-docparser`의 단위 및 통합 테스트를 포함합니다.

## 구조 (Structure)

- `tests/unit/`: 외부 의존성(API, 하드디스크 I/O)이 없는, 모의 객체를 이용한 단위 테스트.
- `tests/integration/`: 실제 PDF 파일 접근 및 로컬 OCR 환경에서의 통신, 예외 처리 점검 테스트용. (현재는 기존 ad-hoc 스크립트들을 보관)
- `tests/fixtures/`: 단위/통합 테스트에서 공용으로 사용할 dummy JSON 및 mock PDF/Markdown 파일들.

## 실행 방법 (Usage)

터미널에서 아래의 명령어를 입력하세요.

### 전체 단위 테스트 (추천)
```bash
# 기본 실행
pytest tests/unit

# 자세한 출력 및 커버리지 포함
pytest tests/unit -v --cov --cov-report=term-missing
# 혹은
scripts\run_tests.bat
```

### 통합 테스트
```bash
pytest tests/integration
```
