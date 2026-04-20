# Phase 5: 단위 1 (API 캐싱 레이어) 구현 결과 보고서

## 1. 개요
본 보고서는 `ps-docparser` 파이프라인 고도화를 위한 **Phase 5의 단위 1 (API 캐싱 레이어) 구현 및 검증 결과**를 요약합니다.
이 과정을 통해 동일한 파일/이미지 입력에 대해서는 고가의 AI OCR 엔진(Z.ai, Mistral) API 호출을 스킵하고 캐시 처리하여 배치 프로파일의 속도와 예산 소모를 획기적으로 최적화했습니다.

---

## 2. 주요 구현 내역 (코드베이스 수정)

| 생성/수정 파일 | 상세 내용 |
| --- | --- |
| **[NEW] `cache/__init__.py`** | `cache` 디렉토리를 패키지로 인식하도록 추가 |
| **[NEW] `cache/table_cache.py`** | SQLite 기반 독립 모듈 (`TableCache`) 구현. <br>- Base64 (data URI) 대신 **원본 파일/이미지 바이트의 청크 단위 해싱(SHA-256)**을 통해 메모리 부하 제로화 <br>- TTL 속성으로 오래된 캐시 관리 지원 |
| **[NEW] `test_phase5_unit1.py`** | 작성 기반을 보장하는 API 모의 분리형 단위 테스트 모음 (`TC-1` ~ `TC-10`) |
| **[NEW] `.gitignore`** | 캐시 DB 폴더(`.cache/`)를 무시하여 저장소 오염 방지 |
| **[MOD] `config.py`** | `CACHE_TTL_DAYS`, `CACHE_ENABLED`, `CACHE_DIR` 3종류 전역 상수 구성 추가 |
| **[MOD] `engines/base_engine.py`** | `cache: TableCache \| None = None` 속성 추가로 하위 엔진에서 공통 접근할 수 있게 확장 |
| **[MOD] `engines/zai_engine.py`** | `ocr_document()`(파일 통채 OCR) 및 `ocr_image()`(PIL 이미지 단건) 메서드 분기 라인에 캐시 스킵 레이어 삽입 |
| **[MOD] `engines/mistral_engine.py`** | Mistral API 포맷에 맞춰 `ocr_document()`에 파일 단계의 캐시 및 페이지별 직렬화/저장 레이어 주입 완료 |

---

## 3. 단위 검증 (Test Coverage)
순수 Python 표준 라이브러리만을 활용하여 작성한 `test_phase5_unit1.py`를 통해 **독립적이고 즉각적인 검증**을 달성했습니다.
특히 Windows 콘솔에서 발생했던 Unicode 이모지 깨짐 및 SQLite WAL(Write-Ahead Logging) 모드로 인한 OS 임시 파일 잠금(Lock) 간섭을 디버깅 및 명시적 `.close()`로 해결하여 안정성을 높였습니다.

### 검증 결과 로그 (성공: 28 / 28)
```text
============================================================
  단위 1: API 캐싱 레이어 검증
============================================================

[TC-1] 초기화
  [OK] DB 파일 생성 -- C:\Users\Public\Documents\ESTsoft\CreatorTemp\...\test_cache.db

[TC-2] 캐시 미스
  [OK] 미스 시 None 반환
  [OK] misses 카운터 증가

[TC-3] 저장 및 적중
  [OK] 저장 후 조회 성공
  [OK] 데이터 무결성 (text)
  [OK] 데이터 무결성 (layout)
  [OK] hits 카운터 증가

[TC-4] 파일 기반 키 생성
  [OK] 키 길이 64자 (sha256 hex)
  [OK] 엔진 다르면 키 다름
  [OK] 페이지 인덱스 있으면 키 다름
  [OK] 동일 파일/엔진 → 동일 키
  [OK] 파일 내용 변경 시 키 변경

[TC-5] 이미지 바이트 기반 키 생성
  [OK] 이미지 키 길이 64자
  [OK] 다른 이미지 → 다른 키
  [OK] 동일 이미지 → 동일 키

[TC-6] TTL 만료
  [OK] 만료 전 조회 성공
  [OK] 만료 후 None 반환

[TC-7] 만료 엔트리 일괄 삭제
  [OK] clear_expired() 실행 성공

[TC-8] 통계
  [OK] stats 키 존재: hits
  [OK] stats 키 존재: misses
  [OK] stats 키 존재: hit_rate_pct
  [OK] stats 키 존재: size
  [OK] hit_rate_pct 범위 [0, 100]

[TC-9] 동일 키 덮어쓰기
  [OK] 덮어쓰기 후 최신 값 반환

[TC-10] config.py 설정 확인
  [OK] CACHE_TTL_DAYS 존재
  [OK] CACHE_ENABLED 존재
  [OK] CACHE_DIR 존재
  [OK] CACHE_DIR는 Path

============================================================
  결과: 28/28 통과 / 0건 실패
============================================================
[완료] 단위 1 검증 -- 모든 테스트 통과
```

## 4. 진행 현황 및 다음 단계
현재 전체 Phase 5 중 **단위 1 (캐싱) 부분이 완전하게 종결**되었습니다.

- **다음 스텝 (단위 2)**: `main.py` 리팩터링 및 배치 파이프라인 통합
  - 기존의 단일 파일 처리 로직(`extract_single_file`)을 분리/재활용하여 폴더 배치(Batch) 처리 지원.
  - 서브프로세스 오버헤드를 완전히 걷어내고 ইন-프로세스 방식으로 성능 도약 및 안정성 추가 확보를 진행할 예정입니다.
