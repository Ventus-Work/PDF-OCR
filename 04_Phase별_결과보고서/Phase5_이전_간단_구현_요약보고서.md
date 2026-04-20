# Phase 5 이전 간단 구현 요약보고서

> 작성일: 2026-04-15
> 목적: Phase 5 계획서 작성 전, 현재까지 완료된 사항과 Phase 5에서 해야 할 일을 종합 파악

---

## 1. Phase 1~4 완료 현황

| Phase | 제목 | 상태 | 핵심 산출물 |
|-------|------|------|-----------|
| Phase 1 | PDF Extractor 이식 | ✅ 완료 | extractors/ + engines/ (PDF→MD) |
| Phase 2 | Standalone Parser 이식 | ✅ 완료 | parsers/ + presets/ (MD→JSON) |
| Phase 3-A | Excel Exporter 기본 + 버그수정 | ✅ 완료 | excel_exporter.py (수정 A~H) |
| Phase 3-B | Exporter 아키텍처 완성 | ✅ 완료 | base_exporter, json_exporter, estimate, detector |
| Phase 4 | BOM 추출 엔진 신규 설계 | ✅ 완료 | OCR 3종 엔진 + 상태머신 + BOM 파이프라인 |

### Phase 4 검증 결과

- 유닛 테스트: **12/12 ALL PASS**
- 배치 테스트: **5/5 ALL PASS** (avg 5.6s/파일)
- BOM 정확도: 도면 표기와 100% 일치 (TOTAL WEIGHT 교차검증)

---

## 2. 현재 코드베이스 실사 결과 (Phase 5 관련)

### 2.1 존재하는 것

| 항목 | 상태 | 비고 |
|------|------|------|
| `batch_test.py` | ✅ 존재 (177줄) | CLI 인수(`--limit`, `--engine`) 지원, TSV/요약 리포트 출력, 프로덕션급 |
| BOM→Excel 출력 | ✅ 작동 확인 | `output/` 디렉토리에 .xlsx 파일 존재 |
| PIPE-BM-PS PDF | ✅ 61개 파일 | 3001~3061, 배치 대상 |
| PIPE-PR2 PDF | ✅ 9개 파일 | PR2-PS-1001~1009, 배관 2D 도면 |
| PIPE-FP PDF | ✅ 7개 파일 | FP-PS-5007~5013, Filter Press |
| `preset_config` 배관 | ⚠️ 부분 | `excel_exporter.py` 파라미터 존재하나 실제 분기 미구현 |

### 2.2 존재하지 않는 것

| 항목 | 상태 | 비고 |
|------|------|------|
| `cache/` 디렉토리 | ❌ 전무 | 캐싱 인프라 없음 |
| `gui.py` | ❌ 전무 | CLI 전용 프로젝트 |
| `main.py --batch` | ❌ 미지원 | 단일 파일만 처리, batch_test.py는 별도 스크립트 |
| `templates/견적서_양식.xlsx` | ❌ 미존재 | estimate 프리셋에서 참조하나 파일 없음 |
| `_write_preset_sheets()` | ❌ 미구현 | excel_exporter.py에 주석만 존재 |
| BOM 집계 기능 | ❌ 전무 | 동일 SIZE+MAT'L 수량 합산 기능 없음 |
| PR2/FP 프리셋 | ❌ 전무 | PDF는 있으나 추출 키워드/프리셋 없음 |

---

## 3. Phase 5 해야 할 일 — 출처별 정리

### 3.1 통합 계획서 원래 Phase 5 범위 (상세_구현_기술서_작성_계획.md §6)

| # | 항목 | 설명 |
|---|------|------|
| 1 | 테이블 캐싱 | `cache/table_cache.py` — sha256(이미지+엔진) 키, SQLite, TTL 30일 |
| 2 | GUI | `gui.py` — tkinter (파일 선택 + 옵션 + 진행바) |
| 3 | 배치처리 | `main.py --batch` — 폴더 일괄 처리 + 요약 리포트 |
| 4 | 캐시 통합 | extractors에 캐시 레이어 주입 |

### 3.2 Phase 4 결과보고서 Next Steps (Phase4_구현_결과보고서.md)

| # | 항목 | 설명 |
|---|------|------|
| 1 | 전체 배치 처리 | PIPE-BM-PS-3001~3061 (60개) 일괄 추출 + 결과 검증 |
| 2 | BOM → Excel 출력 강화 | `--output excel` ExcelExporter 체이닝 |
| 3 | PR2/FP 프리셋 | 배관 도면(PR2), 지지대(FP) 전용 키워드 추가 |
| 4 | 집계 자동화 | 동일 SIZE+MAT'L 수량 합산, 견적가 자동 계산 |
| 5 | GUI 연동 | ocr.py Tkinter GUI를 ps-docparser 파이프라인으로 교체 |

### 3.3 코드베이스 실사에서 발견된 미완성 항목

| # | 항목 | 위치 | 설명 |
|---|------|------|------|
| 1 | 견적서 템플릿 파일 | `templates/견적서_양식.xlsx` | estimate 프리셋에서 참조하나 파일 미생성 |
| 2 | 프리셋 기반 시트 쓰기 | `excel_exporter._write_preset_sheets()` | 파라미터 배관만 연결, 실제 분기 미구현 |
| 3 | K5 레이아웃 테이블 해체 | `table_parser.py` 또는 `excel_exporter.py` | kordoc 알고리즘 미적용 |

---

## 4. Phase 5 후보 항목 (우선순위 정렬)

| 우선순위 | 항목 | 현황 | 필요 작업 | 난이도 |
|---------|------|------|----------|--------|
| **1** | **배치처리 내장** (`--batch`) | `batch_test.py` 존재하나 main.py 미통합 | `main.py`에 `--batch` 인수 추가, 진행률/요약 리포트 내장 | 중 |
| **2** | **전체 BOM 배치** (61개 파일) | 5/61만 테스트 완료 | 60개 전체 일괄 추출 + 결과 검증 + 오류 패턴 분석 | 중 |
| **3** | **API 캐싱** (SQLite) | 전무 | `cache/table_cache.py`, sha256(이미지+엔진) 키, TTL 30일 | 중 |
| **4** | **BOM 집계 자동화** | 전무 | 동일 SIZE+MAT'L 수량 합산, 전체 WEIGHT 집계, 견적가 연계 | 상 |
| **5** | **견적서 Excel 템플릿** | 파일 미존재 + 함수 미구현 | 템플릿 생성 + `_write_preset_sheets()` 구현 | 중 |
| **6** | **PR2/FP 프리셋 확장** | PDF 16개 존재, 프리셋 없음 | 새 preset + 키워드 분석 + 테스트 | 상 |
| **7** | **GUI** (tkinter) | 전무 | 파일 선택 + 엔진 옵션 + 진행바 + 결과 뷰어 | 상 |
| 선택 | **K5 레이아웃 테이블 해체** | 미적용 | 레이아웃 vs 데이터 테이블 자동 감지 | 하 |

---

## 5. 핵심 판단 포인트

### 반드시 해야 하는 것 (Core)

- **`--batch` 내장 + 전체 60개 파일 배치** → 실제 업무 적용의 전제조건
- **API 캐싱** → 60개 파일 x 5.6s x API 비용 절감 필수
- **BOM 집계** → 최종 견적에 필요한 핵심 기능 (동일 자재 수량 합산)

### 하면 좋은 것 (Nice-to-have)

- 견적서 Excel 템플릿 / PR2·FP 프리셋 / GUI / K5 레이아웃 테이블

---

## 6. 기술 자산 현황 (Phase 5 기반)

### 6.1 사용 가능한 PDF 파일

```
전체 77개 PDF
├── PIPE-BM-PS-*.pdf    61개 (BOM 도면, 배치 대상)
├── PIPE-PR2-PS-*.pdf    9개 (배관 2D 도면)
└── PIPE-FP-PS-*.pdf     7개 (Filter Press)
```

### 6.2 output/ 디렉토리 현재 상태

```
output/
├── *.json     6개 (BOM JSON + 견적서 JSON)
├── *.xlsx     2개 (BOM Excel + 견적서 Excel)
├── *.md       6개 (OCR 원문 Markdown)
├── *.docx     2개 (Word 출력)
├── batch_result.tsv     (배치 테스트 결과)
└── batch_summary.txt    (배치 요약)
```

### 6.3 구현 완료된 파일 (Phase 1~4 합계)

```
ps-docparser/ — 총 30+ 파일
├── main.py                     [P1+P2+P3B+P4] 575줄
├── config.py                   [P1+P4] 148줄
├── detector.py                 [P3B+P4] 78줄
│
├── engines/
│   ├── base_engine.py          [P1+P4] 161줄
│   ├── gemini_engine.py        [P1] 187줄
│   ├── local_engine.py         [P1] 55줄
│   ├── zai_engine.py           [P4] 174줄
│   ├── mistral_engine.py       [P4] 104줄
│   └── tesseract_engine.py     [P4] 97줄
│
├── extractors/
│   ├── hybrid_extractor.py     [P1] 238줄
│   ├── text_extractor.py       [P1] 274줄
│   ├── table_utils.py          [P1+P4] 358줄
│   ├── bom_types.py            [P4] 52줄
│   └── bom_extractor.py        [P4] 449줄
│
├── parsers/
│   ├── document_parser.py      [P2] 146줄
│   ├── section_splitter.py     [P2]
│   ├── table_parser.py         [P2] 614줄
│   ├── text_cleaner.py         [P2] 395줄
│   └── bom_table_parser.py     [P4] 320줄
│
├── exporters/
│   ├── base_exporter.py        [P3B] 43줄
│   ├── excel_exporter.py       [P3A+P3B] 706줄
│   └── json_exporter.py        [P3B] 48줄
│
├── presets/
│   ├── pumsem.py               [P2] 107줄
│   ├── estimate.py             [P3B] 131줄
│   └── bom.py                  [P4] 139줄
│
├── utils/
│   ├── ocr_utils.py            [P4] 64줄
│   ├── markers.py              [P1]
│   ├── page_spec.py            [P1]
│   ├── text_formatter.py       [P1]
│   └── usage_tracker.py        [P1]
│
├── test_phase4_unit.py         [P4] 256줄
└── batch_test.py               [P4] 177줄
```

---

> 작성일: 2026-04-15 | Phase 5 계획서 작성 전 사전 분석 자료
