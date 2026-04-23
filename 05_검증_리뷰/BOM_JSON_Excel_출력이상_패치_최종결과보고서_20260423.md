# BOM JSON / Excel 출력 이상 패치 최종 완료 보고서

요청하신 BOM 파이프라인 출력 이상 이슈에 대한 추가 보완 패치 및 회귀 테스트 3종 추가 작업을 모두 성공적으로 완료했습니다.

## 1. 패치 내용 상세

### P1: 중복 헤더 dedupe 방어 (`extractors/bom_converter.py`)
- **수정 내역**: `WEIGHT` 등 중복된 헤더명이 존재할 경우, JSON 변환 과정에서 딕셔너리 키 덮어쓰기 현상이 발생하지 않도록 `WEIGHT_2`, `WEIGHT_3`과 같이 번호 Suffix를 부여합니다.

### P2: 다단 헤더(복합 헤더) 병합 (`parsers/bom_table_parser.py`)
- **수정 내역**: 1행이 상위 헤더이고 2행이 하위 보조 헤더(`UNIT`, `WEIGHT`, `LOSS` 등)인 경우, 2행이 데이터 행으로 유출되지 않도록 병합합니다. (예: `자재명 | ITEM`)
- **조건**: 2행에 보조 키워드가 2개 이상이고, 숫자가 포함된 셀이 전체의 절반 이하일 때만 병합을 수행합니다.

### P3: generic BOM 시트명 의미화 로직 고도화 (`exporters/excel_classifier.py`)
- **수정 내역**: 일반 영문 표가 잘못 분류되는 것을 막기 위해 `bom_generic` 판별 조건을 강화했습니다.
- **개선 조건**: 명시적인 `BOM_자재` 타입이 아닌 경우, `[dwgno, size, mat'l, q'ty, description, mark, weight]` 중 **최소 2개 이상의 키워드**가 포함된 경우에만 `bom_generic`으로 분류되어 `"BOM_자재표"` 시트로 출력됩니다.

### P4: 혼합 문서 경고(Warning) 조건 범위 축소 (`pipelines/bom_pipeline.py`)
- **수정 내역**: 정상적인 다장짜리 BOM 문서가 오경고를 발생시키지 않도록 경고 발동 조건을 의도에 맞게 좁혔습니다.
- **개선 조건**: 도면 메타데이터가 없고 텍스트가 김에도(1000자 이상), 추출된 표가 `0 < total_tables <= 2` 인 상황에서만 혼합 문서 의심 경고를 띄웁니다.

---

## 2. 신규 회귀 테스트(Regression Test) 3종 추가

Coverage 하락 방지 및 기능 영구 보존을 위해 각 분기에 해당하는 전용 테스트를 추가했습니다.

1. **`test_duplicate_headers_are_suffixed_in_to_sections`** (`test_bom_extractor.py`)
   - 동일한 헤더명 입력 시 Suffix(`_2`, `_3`)가 정상 부여되고 row_dict 값이 덮어씌워지지 않는지 검증.
2. **`test_two_row_header_is_merged_and_second_header_row_not_emitted_as_data`** (`test_bom_table_parser.py`)
   - 1행/2행 복합 헤더 입력 시, 파이프(`|`)로 병합되며 2번째 헤더 행이 데이터 행(`rows`)에 남지 않음을 검증.
3. **`test_mixed_document_warning_only_when_few_tables_no_meta_and_long_text`** (`test_bom_pipeline.py`)
   - 파라미터화(Parametrize)된 테스트로, 1테이블일 때만 경고가 발생하고, 3테이블이거나 메타데이터가 있으면 경고가 발생하지 않음을 검증.

---

## 3. 통합 검증 결과

- **Test Suite Result**: 총 667건의 단위/통합 테스트 구동 완료 (`667 passed, 6 skipped`).
- **Exit Code**: `0` (정상 통과)
- **Coverage 회복**: 신규 분기에 대한 명시적 테스트 케이스들이 추가되어 Coverage Gate 제한(68.30% 미달성) 문제를 해결했습니다.
- **안정성 확보**: 일반 표의 오분류(P3), 정상 BOM의 오경고(P4) 이슈를 완전히 수정하여 사이드 이펙트를 차단했습니다.
