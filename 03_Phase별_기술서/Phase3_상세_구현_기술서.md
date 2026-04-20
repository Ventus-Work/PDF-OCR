# Phase 3 상세 구현 기술서 — 출력 엔진(Exporters) + 견적서 프리셋 + 문서 감지기

## 목적

Phase 2까지 완성된 **PDF → MD → JSON** 파이프라인의 최종 출력물(JSON)을 **Excel(.xlsx)** 로 변환하는 내보내기(Exporter) 패키지를 구축한다.

동시에, 현재 `pumsem`(건설 품셈) 전용으로만 존재하는 프리셋 체계에 **`estimate`(견적서) 프리셋**을 추가하여, 견적서 문서에 특화된 테이블 분류·금액 집계·표지 메타데이터 추출 로직을 도메인 주입 방식으로 지원한다.

Phase 3 완료 시점에 **`python main.py "견적서.pdf" --output excel --preset estimate` 한 줄로 PDF에서 실제 업무용 Excel 파일이 생성**되어야 한다.

---

## Phase 2 출력물 분석 (Phase 3 입력)

Phase 3의 입력은 Phase 2가 출력하는 JSON 배열이다. 현재 확인된 구조:

```json
[
  {
    "section_id": "doc",
    "title": "파일명.md",
    "department": "",
    "chapter": "",
    "page": 0,
    "source_file": "파일명.md",
    "toc_title": "",
    "clean_text": "본문 텍스트 (테이블 제외)",
    "tables": [
      {
        "table_id": "T-doc-01",
        "type": "A_품셈",
        "headers": ["NO", "명 칭", "규 격", ...],
        "rows": [
          {"NO": "I.", "명 칭": "직접비", ...},
          ...
        ],
        "notes_in_table": ["- 7,521"],
        "raw_row_count": 16,
        "parsed_row_count": 11
      }
    ],
    "notes": [],
    "conditions": [],
    "cross_references": [],
    "revision_year": "",
    "unit_basis": ""
  }
]
```

### 기존 견적서 Excel 시트 구조 (목표 출력)

실제 `고려아연 배관 Support 제작_추가_2차분 견적서.xlsx` 분석 결과:

| 시트명 | 용도 | 구조 |
|---|---|---|
| `갑지` | 견적 표지 | 제출처, 금액, 현장명, 공사명, 견적번호 등 메타 정보 |
| `내역서` | 세부 내역 | 품명/규격/단위/수량 + 재료비·노무비·경비·합계(단가/금액) 13열 구조 |
| `물량산출표` | BOM | 도면구분/Bom코드/철판종류/치수/재질/수량/중량/도장면적 13열 |
| `샘플내역서` | 템플릿 | 내역서와 동일 구조의 참조용 시트 |

---

## Phase 3 신규/변경 파일 목록

```
ps-docparser/
├── main.py                          # [변경] --output excel 옵션 추가
├── config.py                        # [변경 없음]
│
├── engines/                         # [변경 없음]
├── extractors/                      # [변경 없음]
├── utils/                           # [변경 없음]
│
├── parsers/                         # [변경 없음]
│
├── exporters/                       # [신규] Phase 3 전체
│   ├── __init__.py                  # 패키지 초기화
│   ├── base_exporter.py             # 내보내기 공통 인터페이스 (ABC)
│   ├── excel_exporter.py            # JSON → Excel (.xlsx) 변환
│   └── json_exporter.py             # JSON 파일 저장 (기존 main.py 로직 분리)
│
├── templates/                       # [신규] Excel 템플릿 파일
│   └── 견적서_양식.xlsx              # 갑지(표지) 양식 템플릿 (디자이너 편집 가능)
│
├── presets/
│   ├── __init__.py
│   ├── pumsem.py                    # [변경 없음]
│   └── estimate.py                  # [신규] 견적서 프리셋
│
├── detector.py                      # [신규] 문서 유형 자동 감지 (텍스트 기반)
│
└── requirements.txt                 # [변경] openpyxl 추가
```

---

## 파일별 상세 스펙

### 1. `exporters/__init__.py` — 패키지 초기화

```python
"""
exporters/ — 구조화 JSON → 최종 출력 파일 변환 패키지

Why: Phase 2(parsers/)가 생산하는 JSON을 사용자가 실제 업무에서 쓸 수 있는
     Excel, JSON 파일 등으로 변환하는 3단계 처리기.
     각 출력 형식은 독립된 Exporter 클래스로 구현되어 Strategy Pattern으로 교체 가능.
"""
```

---

### 2. `exporters/base_exporter.py` — 내보내기 공통 인터페이스

```python
"""
내보내기 공통 인터페이스 (Abstract Base Class).

Why: Phase 1의 engines/base_engine.py와 동일한 설계 패턴.
     새 출력 형식 추가 시 이 클래스를 상속하면 main.py가 자동으로 인식.
     현재: ExcelExporter, JsonExporter
     향후 확장: CsvExporter, DbExporter (Supabase) 등
"""
from abc import ABC, abstractmethod
from pathlib import Path


class BaseExporter(ABC):
    """출력 파일 생성기의 공통 인터페이스."""

    @abstractmethod
    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        JSON 섹션 리스트를 출력 파일로 변환한다.

        Args:
            sections: Phase 2 출력 JSON 배열 (섹션 리스트)
            output_path: 출력 파일 경로 (.xlsx, .json 등)
            metadata: 문서 메타데이터 (표지 정보 등, 선택적)
            preset_config: 프리셋별 출력 설정 (시트 구성, 열 매핑 등)

        Returns:
            Path: 실제로 저장된 파일 경로
        """
        ...

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """이 Exporter가 생성하는 파일 확장자 (예: '.xlsx')."""
        ...
```

---

### 3. `exporters/excel_exporter.py` — JSON → Excel 변환 (핵심)

```python
"""
JSON → Excel (.xlsx) 변환기.

Why: Phase 2의 JSON 출력은 프로그래밍용 데이터 포맷이다.
     실제 업무에서는 Excel 파일이 필요하다 (거래처 제출, 내부 검토, 인쇄).
     이 모듈이 JSON 테이블 데이터를 업무용 Excel 시트로 재구성한다.

Dependencies: openpyxl
"""
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
from openpyxl.utils import get_column_letter

from exporters.base_exporter import BaseExporter
```

**핵심 함수/클래스:**

```python
class ExcelExporter(BaseExporter):
    """JSON 섹션 리스트를 Excel 워크북으로 변환한다."""

    file_extension = ".xlsx"

    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        Phase 2 JSON → Excel 파일 생성.

        동작 흐름:
            1. Workbook 생성 (템플릿 또는 빈 워크북)
            2. preset_config에 따라 시트 구성 결정
               - preset_config 없음 (범용): 테이블당 1시트
               - preset_config["sheets"] 있음: 프리셋 정의 시트 구조 적용
               - preset_config["template_path"] 있음: 템플릿 파일 로드
            3. 각 시트에 헤더 + 데이터 행 기록
            4. 메타데이터 시트 생성 (metadata 있을 경우)
            5. 스타일링 적용 (헤더 배경, 금액 열 콤마 포맷, 테두리)
            6. 파일 저장
        """
        # 템플릿 파일이 지정된 경우 → 템플릿 로드 (갑지 양식 등 보존)
        template_path = None
        if preset_config:
            template_path = preset_config.get("template_path")

        if template_path and Path(template_path).exists():
            from openpyxl import load_workbook
            wb = load_workbook(template_path)
        else:
            wb = Workbook()
            wb.remove(wb.active)  # 기본 빈 시트 제거

        if preset_config and "sheets" in preset_config:
            self._write_preset_sheets(wb, sections, preset_config, metadata)
        else:
            self._write_generic_sheets(wb, sections)

        # 메타데이터 시트 (문서 정보)
        if metadata:
            self._write_metadata_sheet(wb, metadata)

        wb.save(output_path)
        return output_path

    def _write_generic_sheets(
        self,
        wb: Workbook,
        sections: list[dict],
    ) -> None:
        """
        범용 모드: 테이블마다 독립 시트를 생성한다.

        Why: 프리셋 없이 아무 문서든 넣으면 테이블을 그대로 Excel에 옮겨야 한다.
             사용자가 수동으로 원하는 형태로 재편집할 수 있는 원데이터(raw data) 제공이 목적.

        시트 네이밍 규칙:
            - 테이블이 1개: "Table"
            - 테이블이 N개: "Table_1", "Table_2", ...
            - 시트명 31자 제한 (Excel 한계) → 자동 truncate
        """
        table_idx = 0
        for section in sections:
            for table in section.get("tables", []):
                table_idx += 1
                sheet_name = self._safe_sheet_name(
                    f"Table_{table_idx}" if table_idx > 1 else "Table"
                )
                ws = wb.create_sheet(title=sheet_name)
                self._write_table_to_sheet(ws, table)

        # 테이블 없는 경우 → 본문 텍스트만 시트에 기록
        if table_idx == 0:
            ws = wb.create_sheet(title="Content")
            for i, section in enumerate(sections):
                text = section.get("clean_text", "")
                if text:
                    ws.cell(row=i + 1, column=1, value=text)

    def _write_preset_sheets(
        self,
        wb: Workbook,
        sections: list[dict],
        preset_config: dict,
        metadata: dict | None,
    ) -> None:
        """
        프리셋 모드: 프리셋이 정의한 시트 구조에 맞춰 데이터를 배치한다.

        Why: 견적서는 "갑지 + 내역서" 2시트 구조가 표준이다.
             프리셋이 시트별 열 매핑, 행 필터링 규칙을 제공하면
             이 함수가 JSON 데이터를 해당 구조에 맞춰 재배치한다.

        preset_config["sheets"] 구조:
            [
                {
                    "name": "갑지",
                    "type": "cover",       # 표지 시트
                    "fields": {...}        # 메타데이터 → 셀 매핑
                },
                {
                    "name": "내역서",
                    "type": "detail",      # 상세 내역 시트
                    "source_table": 2,     # T-doc-03 (3번째 테이블, 0-indexed: 2)
                    "start_row": 1,        # 데이터 시작 행 (기본: 1)
                }
            ]
        """
        for sheet_def in preset_config["sheets"]:
            sheet_type = sheet_def["type"]

            # [v3 버그 수정] 템플릿에 동명 시트가 이미 존재하면 가져오고(Get),
            # 없으면 새로 생성(Create)한다.
            # Why: openpyxl의 create_sheet()는 동명 시트 존재 시 "갑지1"처럼
            #      자동 넘버링된 빈 시트를 만들어버린다. 템플릿의 원본 시트가
            #      사용되지 않고 빈 시트에 데이터가 기록되는 치명적 버그 방지.
            sheet_name = sheet_def["name"]
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
            else:
                ws = wb.create_sheet(title=sheet_name)

            if sheet_type == "cover":
                self._write_cover_sheet(ws, metadata, sheet_def.get("fields", {}))
            elif sheet_type == "detail":
                self._write_detail_sheet(ws, sections, sheet_def)
            elif sheet_type == "summary":
                self._write_summary_sheet(ws, sections, sheet_def)

    # ── 시트 작성 헬퍼 ──

    def _write_table_to_sheet(
        self,
        ws,
        table: dict,
        *,
        start_row: int = 1,
    ) -> None:
        """
        단일 테이블을 워크시트에 기록한다.

        [v3 start_row 파라미터 추가]
        Why: 템플릿 시트의 상단에 회사 로고/결재칸 등이 있을 경우
             1행부터 덮어쓰면 양식이 깨진다. start_row로 시작 위치를
             지정할 수 있게 하되, 기본값은 1 (빈 시트에서의 정상 동작 유지).
             현재 내역서는 코드 생성 시트이므로 start_row=1이 기본.
             향후 내역서도 템플릿화할 경우 sheet_def에 start_row를 지정하면 된다.

        Args:
            ws: 대상 워크시트
            table: Phase 2 테이블 dict (headers, rows)
            start_row: 헤더를 기록할 시작 행 (기본: 1)

        동작:
            1. 헤더 행 기록 (볼드, 배경색) — start_row 위치
            2. 데이터 행 기록 (dict → 열 순서 매핑) — start_row + 1부터
            3. 열 너비 자동 조정
            4. 금액 열 감지 → 숫자 포맷(#,##0) 적용
        """
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        # 헤더 기록
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx, value=header)
            cell.font = Font(bold=True, size=10)
            cell.fill = PatternFill(start_color="D9E1F2", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # 데이터 행 기록
        data_start = start_row + 1
        for row_idx, row_data in enumerate(rows, data_start):
            for col_idx, header in enumerate(headers, 1):
                value = row_data.get(header, "")
                cell = ws.cell(row=row_idx, column=col_idx)

                # 금액/수치 열 감지 및 숫자 변환
                numeric_val = self._try_parse_number(value)
                if numeric_val is not None:
                    cell.value = numeric_val
                    cell.number_format = '#,##0'
                else:
                    cell.value = value

        # 열 너비 자동 조정
        self._auto_fit_columns(ws, headers)

        # 테두리 적용
        total_rows = start_row + len(rows)  # 헤더 + 데이터
        self._apply_borders(ws, len(headers), total_rows)

    def _write_cover_sheet(
        self,
        ws,
        metadata: dict | None,
        field_map: dict,
    ) -> None:
        """
        표지(갑지) 시트를 생성한다.

        [v2 설계 변경] 갑지는 회사 양식(로고, 결재선, 셀 병합 등)이 포함된
        정형 문서이므로 코드로 처음부터 그리지 않는다.

        동작 방식:
            1. template_path가 지정된 경우:
               → 템플릿 .xlsx에서 갑지 시트를 그대로 가져온 상태.
               → field_map의 셀 주소에 메타데이터 값만 주입한다.
               → 양식 디자인 변경 시 .xlsx 파일만 수정하면 되므로 코드 수정 불필요.
            2. template_path가 없는 경우:
               → 빈 시트에 key-value만 기록 (범용 폴백).

        field_map 예시:
            {
                "title": "A1",
                "date": "I3",
                "client": "C4",
                "amount": "C5",
                "project": "C6",
                "description": "C7",
                "serial_no": "C9",
            }
        """
        if not metadata:
            ws.cell(row=1, column=1, value="(메타데이터 없음)")
            return

        for key, cell_ref in field_map.items():
            value = metadata.get(key, "")
            if value:
                ws[cell_ref] = value

    def _write_detail_sheet(
        self,
        ws,
        sections: list[dict],
        sheet_def: dict,
    ) -> None:
        """
        상세 내역 시트를 생성한다.

        sheet_def 구조:
            {
                "name": "내역서",
                "type": "detail",
                "source_table_type": "A_품셈",  # 이 type의 테이블만 선택
                "source_table_index": -1,        # -1 = 헤더매칭+행수 복합 스코어링
                "start_row": 1,                  # 데이터 시작 행 (기본: 1)
                # 향후 확장: "column_map": {"품명": "A", "규격": "B", ...}
                # → 내역서도 템플릿화할 경우 JSON 키 → Excel 열 매핑 지원 예정
            }
        """
        # 대상 테이블 선택
        target_table = self._select_table(sections, sheet_def)
        if not target_table:
            ws.cell(row=1, column=1, value="(해당 테이블 없음)")
            return

        start_row = sheet_def.get("start_row", 1)
        self._write_table_to_sheet(ws, target_table, start_row=start_row)

    def _write_summary_sheet(
        self,
        ws,
        sections: list[dict],
        sheet_def: dict,
    ) -> None:
        """
        요약 시트를 생성한다 (견적서 요약 내역 등).
        """
        target_table = self._select_table(sections, sheet_def)
        if not target_table:
            ws.cell(row=1, column=1, value="(해당 테이블 없음)")
            return
        self._write_table_to_sheet(ws, target_table)

    def _write_metadata_sheet(
        self,
        wb: Workbook,
        metadata: dict,
    ) -> None:
        """
        문서 메타데이터를 별도 시트에 기록한다.

        Why: 표지(갑지)로 재구성되지 않은 원본 메타데이터를
             key-value 형태로 보존하여 추적성을 제공한다.
        """
        ws = wb.create_sheet(title="메타데이터")
        ws.cell(row=1, column=1, value="항목").font = Font(bold=True)
        ws.cell(row=1, column=2, value="값").font = Font(bold=True)

        for idx, (key, value) in enumerate(metadata.items(), 2):
            ws.cell(row=idx, column=1, value=key)
            ws.cell(row=idx, column=2, value=str(value))

        self._auto_fit_columns(ws, ["항목", "값"])

    # ── 유틸리티 ──

    # ── 테이블 자동 선택용 헤더 키워드 (견적서 내역) ──
    # Why: 행 수만으로 테이블을 선택하면 부속 자료(장비 리스트, 규격표 등)를
    #      내역서로 오인할 수 있다. 헤더 매칭 점수를 1차 기준으로 사용하여
    #      견적 내역 테이블을 정확히 식별한다.
    HEADER_SCORE_KEYWORDS = {"품명", "규격", "단위", "수량", "단가", "금액", "합계", "명 칭"}

    def _select_table(
        self,
        sections: list[dict],
        sheet_def: dict,
    ) -> dict | None:
        """
        sheet_def의 조건에 맞는 테이블을 섹션 리스트에서 선택한다.

        [v2 선택 알고리즘] 3단계 스코어링:
            1. source_table_index 직접 지정 시 → 해당 인덱스 (무조건)
            2. source_table_type 필터링 → 해당 type만 후보로 남김
            3. 후보 중 (헤더 매칭 점수, 행 수) 복합 기준으로 최대 테이블 선택
               - 1차: 헤더에 HEADER_SCORE_KEYWORDS 몇 개 포함되는지 (가중치 높음)
               - 2차: 동점 시 parsed_row_count가 큰 것

        Why: 행 수만으로 선택하면, 견적서 뒤에 딸려온 규격표(행 수 많음)를
             내역서로 오인하는 위험이 있다. 헤더 키워드 매칭을 1차 기준으로
             사용하면, "품명/규격/수량/금액" 등 견적 내역 컬럼이 있는 테이블이
             우선 선택된다.
        """
        all_tables = []
        for section in sections:
            all_tables.extend(section.get("tables", []))

        if not all_tables:
            return None

        # 직접 인덱스 지정
        idx = sheet_def.get("source_table_index")
        if idx is not None and idx != -1:
            return all_tables[idx] if idx < len(all_tables) else None

        # type 필터링
        table_type = sheet_def.get("source_table_type")
        if table_type:
            filtered = [t for t in all_tables if t.get("type") == table_type]
            if not filtered:
                return None
            all_tables = filtered

        # 복합 스코어링: (헤더 매칭 점수, 행 수)
        def _score(table: dict) -> tuple[int, int]:
            headers = set(table.get("headers", []))
            header_match = len(headers & self.HEADER_SCORE_KEYWORDS)
            row_count = table.get("parsed_row_count", 0)
            return (header_match, row_count)

        return max(all_tables, key=_score)

    @staticmethod
    def _try_parse_number(value: str) -> int | float | None:
        """
        문자열을 숫자로 변환 시도한다. 실패 시 None 반환.

        Why: Phase 2에서 try_numeric()을 의도적으로 제거했다(데이터 무결성 보호).
             Excel 출력 단계에서만 숫자 변환을 명시적으로 수행한다.
             이 함수의 위치가 exporters/에 있는 것이 핵심 설계 의도이다.

        변환 규칙:
            - "15,000,000" → 15000000 (int)  — 콤마 제거 후 정수
            - "3.14" → 3.14 (float)
            - "0015" → None (선행 0 → 식별자로 간주, 변환 안 함)
            - "" → None
            - "SUS304" → None (변환 실패)
            - "-" → None (대시 단독)
        """
        if not isinstance(value, str) or not value.strip():
            return None

        val = value.strip()

        # 대시 단독은 무시
        if val == "-":
            return None

        # 선행 0 보호 (식별자/코드)
        # "0015" → 변환 안 함. "0.5" → 변환 허용. "0" → 변환 허용.
        stripped = val.replace(",", "").lstrip("-")
        if len(stripped) > 1 and stripped[0] == "0" and stripped[1] != ".":
            return None

        # 콤마 제거 후 변환
        numeric_str = val.replace(",", "")
        try:
            if "." in numeric_str:
                return float(numeric_str)
            return int(numeric_str)
        except ValueError:
            return None

    @staticmethod
    def _safe_sheet_name(name: str) -> str:
        """Excel 시트명 규칙에 맞게 정제한다 (31자 제한, 금칙 문자 제거)."""
        # Excel 금칙 문자: \ / * ? : [ ]
        for ch in r'\/*?:[]':
            name = name.replace(ch, "_")
        return name[:31]

    @staticmethod
    def _auto_fit_columns(ws, headers: list[str]) -> None:
        """열 너비를 내용에 맞게 자동 조정한다."""
        for col_idx in range(1, len(headers) + 1):
            max_len = 0
            col_letter = get_column_letter(col_idx)
            for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
                for cell in row:
                    if cell.value:
                        # 한글은 2바이트 폭으로 계산
                        cell_len = sum(
                            2 if ord(c) > 127 else 1
                            for c in str(cell.value)
                        )
                        max_len = max(max_len, cell_len)
            ws.column_dimensions[col_letter].width = min(max_len + 4, 50)

    @staticmethod
    def _apply_borders(ws, num_cols: int, num_rows: int) -> None:
        """전체 데이터 범위에 얇은 테두리를 적용한다."""
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )
        for row in ws.iter_rows(min_row=1, max_row=num_rows,
                                min_col=1, max_col=num_cols):
            for cell in row:
                cell.border = thin_border
```

---

### 4. `exporters/json_exporter.py` — JSON 파일 저장 (main.py 로직 분리)

```python
"""
JSON 파일 저장 Exporter.

Why: 현재 main.py에 인라인으로 작성된 json.dump() 호출을
     BaseExporter 인터페이스에 맞춰 분리한다.
     향후 JSON 포맷 옵션(compact, pretty, JSONL 등)을 확장할 수 있다.

원본: main.py L385~386 (json.dump 호출)
"""
import json
from pathlib import Path
from exporters.base_exporter import BaseExporter


class JsonExporter(BaseExporter):
    """JSON 섹션 리스트를 파일로 저장한다."""

    file_extension = ".json"

    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        JSON 파일로 저장한다.

        metadata가 있으면 최상위에 문서 메타데이터를 병합한다:
            {
                "metadata": {...},
                "sections": [...]
            }

        metadata가 없으면 기존 동작 유지 (섹션 배열만 저장):
            [...]
        """
        if metadata:
            output_data = {
                "metadata": metadata,
                "sections": sections,
            }
        else:
            output_data = sections

        with open(output_path, "w", encoding="utf-8-sig") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        return output_path
```

---

### 5. `presets/estimate.py` — 견적서 프리셋 (신규)

```python
"""
presets/estimate.py — 견적서(estimate) 전용 프리셋 설정

Why: 견적서 PDF는 품셈 문서와 전혀 다른 도메인 규칙을 가진다.
     - 갑지(표지) + 내역서 2시트 구조가 표준
     - 금액 열은 항상 콤마 포맷
     - 합계/소계 행은 특수 스타일 적용
     - 표지에서 메타데이터(제출처, 금액, 공사명 등) 추출 필요

     이 파일은 견적서 도메인 전용 설정만 담는다.
     범용 파이프라인의 parsers/에는 영향을 주지 않는다.
"""

import re


# ══════════════════════════════════════════════════════════
# 1. 테이블 유형 분류 키워드
# ══════════════════════════════════════════════════════════

TABLE_TYPE_KEYWORDS = {
    # 견적 요약 테이블 (직접비/간접비/합계 구조)
    "E_견적요약": ["직접비", "간접비", "합계", "소계", "총 합 계"],
    # 견적 상세 내역 (재료비/노무비/경비 분리 구조)
    "E_견적내역": ["재료비", "노무비", "경비", "합계", "단가", "금액"],
    # 일반사항/특기사항
    "E_견적조건": ["일반사항", "특기사항", "납품", "결제조건"],
}


# ══════════════════════════════════════════════════════════
# 2. 표지(갑지) 메타데이터 추출 패턴
#
# Why: 견적서 표지의 본문 텍스트에서 key-value 정보를 정규식으로 추출한다.
#      Phase 2의 clean_text 필드가 입력이다.
# ══════════════════════════════════════════════════════════

COVER_PATTERNS = {
    # "제 출 처 : 창녕공장"  → client = "창녕공장"
    "client": re.compile(
        r'제\s*출\s*처\s*[:：]\s*(.+?)(?:\s*貴中|\s*$)', re.MULTILINE
    ),
    # "견적금액 : ₩16,700,000 원정" → amount_text = "₩16,700,000 원정"
    "amount_text": re.compile(
        r'견적금액\s*[:：]\s*(.+?)(?:\s*원정|\s*$)', re.MULTILINE
    ),
    # "현 장 명 : 대기오염방지시설 ..." → project = "대기오염방지시설 ..."
    "project": re.compile(
        r'현\s*장\s*명\s*[:：]\s*(.+?)$', re.MULTILINE
    ),
    # "공 사 명 : 고려아연 배관 ..." → description = "고려아연 배관 ..."
    "description": re.compile(
        r'공\s*사\s*명\s*[:：]\s*(.+?)(?:\s*경남|\s*$)', re.MULTILINE
    ),
    # "물 품 명 : 배관 Support" → item = "배관 Support"
    "item": re.compile(
        r'물\s*품\s*명\s*[:：]\s*(.+?)(?:\s*대표|\s*$)', re.MULTILINE
    ),
    # "견적일련번호 : PSQ26-0406-59" → serial_no = "PSQ26-0406-59"
    "serial_no": re.compile(
        r'견적일련번호\s*[:：]\s*(\S+)', re.MULTILINE
    ),
}


def extract_cover_metadata(clean_text: str) -> dict:
    """
    견적서 표지 텍스트에서 메타데이터를 추출한다.

    [v2 경고 로그 추가]
    정규식 매칭 실패 시 개별 필드를 콘솔에 경고 출력한다.
    AI Fallback은 불채택 (Phase 3 입력은 이미 AI를 거친 정제 텍스트이므로
    추가 API 호출은 비용·지연 이중 발생. 정규식 범위 확대로 커버 가능).

    Args:
        clean_text: Phase 2 출력의 section["clean_text"]

    Returns:
        dict: {
            "client": "창녕공장",
            "amount_text": "₩16,700,000",
            "amount": 16700000,           # 숫자 파싱 결과 (실패 시 None)
            "project": "대기오염방지시설 ...",
            "description": "고려아연 배관 Support ...",
            "item": "배관 Support",
            "serial_no": "PSQ26-0406-59",
        }
    """
    result = {}
    failed_keys = []
    for key, pattern in COVER_PATTERNS.items():
        match = pattern.search(clean_text)
        if match:
            result[key] = match.group(1).strip()
        else:
            result[key] = ""
            failed_keys.append(key)

    # 매칭 실패 필드 경고 (AI Fallback 대신 경고 로그로 처리)
    if failed_keys:
        print(f"   ⚠️ 표지 메타 추출 실패 필드: {', '.join(failed_keys)}")
        print(f"       → 정규식 패턴 확인 필요. clean_text 앞 200자: {clean_text[:200]}")

    # 금액 숫자 파싱
    amount_str = result.get("amount_text", "")
    amount_digits = re.sub(r'[^\d]', '', amount_str)
    result["amount"] = int(amount_digits) if amount_digits else None

    return result


# ══════════════════════════════════════════════════════════
# 3. Excel 출력 시트 구성 정의
#
# Why: ExcelExporter._write_preset_sheets()가 이 구성을 읽어
#      견적서 표준 양식(갑지+내역서)에 맞춰 시트를 생성한다.
# ══════════════════════════════════════════════════════════

EXCEL_SHEET_CONFIG = {
    # [v2 추가] 갑지(표지)는 템플릿 파일에서 양식을 가져온다.
    # Why: 갑지는 회사 로고, 결재선, 셀 병합 등 복잡한 양식이라
    #      코드로 처음부터 그리는 것보다 템플릿에 데이터만 주입하는 방식이 적합.
    #      양식 변경 시 .xlsx 파일만 수정하면 되므로 코드 수정 불필요.
    #      내역서(데이터 시트)는 행 수가 동적이므로 코드 생성을 유지한다.
    "template_path": "templates/견적서_양식.xlsx",

    "sheets": [
        {
            "name": "갑지",
            "type": "cover",
            "fields": {
                "title": "A1",
                "date": "I3",
                "client": "C4",
                "amount": "C5",
                "project": "C6",
                "description": "C7",
                "item": "C8",
                "serial_no": "C9",
            },
        },
        {
            "name": "내역서",
            "type": "detail",
            "source_table_type": "A_품셈",     # A_품셈 타입 중 자동 선택
            "source_table_index": -1,          # -1 = 헤더 매칭 + 행 수 복합 스코어링
        },
        {
            "name": "요약",
            "type": "summary",
            "source_table_index": 0,           # 첫 번째 테이블 (요약 내역)
        },
    ],
}


# ══════════════════════════════════════════════════════════
# 4. 합계/소계 행 감지 패턴
#
# Why: Excel 출력 시 합계/소계 행에 시각적 강조(볼드, 배경색)를
#      자동으로 적용하기 위한 행 감지 패턴.
# ══════════════════════════════════════════════════════════

SUMMARY_ROW_KEYWORDS = [
    "소 계", "소계", "합 계", "합계", "총 합 계", "총합계",
    "직접비", "간접비", "일반관리비",
]


def is_summary_row(row_data: dict) -> bool:
    """행이 합계/소계 행인지 판별한다."""
    for value in row_data.values():
        if isinstance(value, str):
            for keyword in SUMMARY_ROW_KEYWORDS:
                if keyword in value:
                    return True
    return False


# ══════════════════════════════════════════════════════════
# 공개 인터페이스 (main.py에서 호출)
# ══════════════════════════════════════════════════════════

def get_table_type_keywords() -> dict:
    """견적서 프리셋의 테이블 유형 분류 키워드를 반환한다."""
    return TABLE_TYPE_KEYWORDS


def get_excel_config() -> dict:
    """견적서 프리셋의 Excel 시트 구성(preset_config)을 반환한다."""
    return EXCEL_SHEET_CONFIG


def get_cover_patterns() -> dict:
    """견적서 프리셋의 표지 추출 패턴(COVER_PATTERNS)을 반환한다."""
    return COVER_PATTERNS
```

---

### 6. `detector.py` — 문서 유형 자동 감지 (텍스트 기반)

```python
"""
detector.py — 문서 유형 자동 감지기 (텍스트 기반)

[v2 아키텍처 수정]
기존 설계: PDF 파일을 pdfplumber로 직접 열어 텍스트 추출 후 판별.
문제점:
  1. Phase 1(extractors/) 계층을 우회하는 아키텍처 위배.
  2. 이미지 스캔본 PDF에서는 pdfplumber.extract_text()가
     빈 문자열을 반환 → 감지 실패.

수정 설계: Phase 1 추출 완료 후의 마크다운 텍스트(MD 문자열)를
           입력으로 받아 키워드 매칭으로 문서 유형을 판별한다.
           → pdfplumber 직접 호출 제거, 추출 계층 아키텍처 준수.
           → 이미지 스캔본도 Phase 1 AI(Gemini) 처리 후의
             텍스트가 들어오므로 정상 감지 가능.

위치: ps-docparser/detector.py (최상위)
Dependencies: 없음 (순수 문자열 처리)
"""


def detect_document_type(text: str) -> str | None:
    """
    추출된 텍스트를 분석하여 문서 유형을 추정한다.

    Args:
        text: Phase 1 추출 결과 (MD 문자열) 또는 Phase 2의 clean_text.
              PDF를 직접 열지 않는다. 호출부가 텍스트를 전달할 책임.

    Returns:
        str | None:
            - "estimate" → 견적서로 추정 (견적금액, 見積, 내역서 등 키워드 감지)
            - "pumsem"   → 품셈 문서로 추정 (수량산출, 품셈, 부문 등 키워드 감지)
            - None       → 판별 불가 (범용 모드 유지)

    판별 로직:
        1. 전달받은 텍스트에서 키워드 매칭으로 문서 유형 점수 계산
        2. 점수가 임계치 이상이면 해당 유형 반환
    """
    if not text or not text.strip():
        return None

    # ── 견적서 키워드 ──
    estimate_keywords = [
        "見積", "견적", "견적금액", "내역서", "납품기일",
        "결제조건", "견적유효기간", "직접비", "간접비",
    ]
    estimate_score = sum(1 for kw in estimate_keywords if kw in text)

    # ── 품셈 키워드 ──
    pumsem_keywords = [
        "품셈", "수량산출", "부문", "제6장", "단위당",
        "적용기준", "노무비", "참조", "보완",
    ]
    pumsem_score = sum(1 for kw in pumsem_keywords if kw in text)

    # 임계치: 3개 이상 키워드 매칭 시 판별
    THRESHOLD = 3

    if estimate_score >= THRESHOLD and estimate_score > pumsem_score:
        return "estimate"
    elif pumsem_score >= THRESHOLD and pumsem_score > estimate_score:
        return "pumsem"

    return None


def suggest_preset(text: str) -> str:
    """
    사용자에게 보여줄 프리셋 제안 메시지를 생성한다.

    Args:
        text: Phase 1 추출 결과 텍스트 (MD 문자열)

    Returns:
        str: 제안 메시지 (빈 문자열 = 제안 없음)
    """
    detected = detect_document_type(text)
    if detected == "estimate":
        return "💡 견적서로 감지되었습니다. --preset estimate 를 추가하면 견적서 양식으로 출력됩니다."
    elif detected == "pumsem":
        return "💡 품셈 문서로 감지되었습니다. --preset pumsem --toc <목차파일> 을 추가하면 품셈 양식으로 출력됩니다."
    return ""
```

---

### 7. `main.py` — 확장 (Excel 출력 + 견적서 프리셋)

**변경 범위:**

| 변경 항목 | 내용 |
|---|---|
| CLI 인수 확장 | `--output` 선택지에 `excel` 추가 (md/json/excel) |
| 프리셋 확장 | `--preset estimate` 선택지 추가 |
| Exporter 분기 | `--output` 값에 따라 ExcelExporter / JsonExporter 인스턴스 선택 |
| 문서 감지 | `--preset` 미지정 시 Phase 1 추출 결과 텍스트로 `detector.suggest_preset()` 호출 (⚠️ Phase 1 완료 후 시점) |
| 메타데이터 추출 | `--preset estimate` 시 `extract_cover_metadata()` 호출 |

**CLI 인수 (변경 후):**

```
python main.py <파일> [옵션]

필수:
  <파일>                  PDF 파일 (.pdf) 또는 마크다운 파일 (.md) 또는 JSON 파일 (.json)

옵션:
  --engine <이름>         AI 엔진 (gemini|local, 기본: .env의 DEFAULT_ENGINE)
  --text-only, -t        텍스트 전용 모드 (AI 없음, 무료)
  --toc <파일>            목차 파일 (.json 또는 .txt)
  --pages <지정>          페이지 범위 (PDF 입력 시에만 적용)
  --output <형식>         출력 형식 (md|json|excel, 기본: md)           ← [변경]
  --output-dir <경로>     출력 폴더 (기본: ./output/)
  --preset <이름>         도메인 프리셋 (pumsem|estimate, 기본: 없음)   ← [변경]
```

**동작 흐름 (변경 후):**

```
[입력이 .pdf인 경우]
  --output md     → PDF 추출 → MD 저장 (기존)
  --output json   → PDF 추출 → MD → JSON 저장 (기존)
  --output excel  → PDF 추출 → MD → JSON → Excel 저장         ← [신규]

[입력이 .md인 경우]
  --output md     → 에러 ("이미 마크다운입니다")
  --output json   → 파서 실행 → JSON 저장 (기존)
  --output excel  → 파서 실행 → JSON → Excel 저장              ← [신규]

[입력이 .json인 경우]                                           ← [신규]
  --output md     → 에러
  --output json   → 에러 ("이미 JSON입니다")
  --output excel  → JSON 로드 → Excel 저장
```

**main.py 변경 코드 핵심 부분:**

```python
# ── argparse 변경 ──
parser.add_argument(
    "--output",
    default="md",
    choices=["md", "json", "excel"],          # excel 추가
    dest="output_format",
    help="출력 형식 (기본: md) — json/excel 시 Phase 2+3 실행",
)
parser.add_argument(
    "--preset",
    default=None,
    choices=["pumsem", "estimate"],           # estimate 추가
    help="도메인 프리셋 (기본: 없음=범용)",
)

# ── .json 입력 지원 (Phase 3 신규) ──
is_json_input = input_path.lower().endswith(".json")

if is_json_input:
    if args.output_format != "excel":
        print("⚠️  .json 파일 입력 시 --output excel 을 사용하세요.")
        sys.exit(1)

    import json as json_lib
    with open(input_path, "r", encoding="utf-8-sig") as f:
        sections = json_lib.load(f)
    # sections가 {"metadata":..., "sections":...} 구조일 수도 있음
    if isinstance(sections, dict):
        metadata = sections.get("metadata")
        sections = sections.get("sections", [])

# ── 프리셋 로딩 확장 ──
excel_config = None
cover_metadata = None

if preset == "estimate":
    from presets.estimate import (
        get_table_type_keywords as get_est_keywords,
        get_excel_config,
        extract_cover_metadata,
    )
    type_keywords = get_est_keywords()
    excel_config = get_excel_config()
    print(f"📋 프리셋 활성화: {preset} (견적서 테이블 키워드·Excel 시트 구성 로드 완료)")

# ── 문서 감지 (프리셋 미지정 시, Phase 1 추출 완료 후) ──
# [v2 변경] detector.py가 텍스트 기반으로 변경되었으므로
#           PDF 경로가 아닌 추출된 MD 텍스트를 전달한다.
#           Phase 1 완료 후 md_content(추출 결과)가 존재하는 시점에서 호출.
if preset is None and md_content:
    from detector import suggest_preset
    suggestion = suggest_preset(md_content)
    if suggestion:
        print(suggestion)

# ── Phase 3: JSON → Excel (--output excel 시) ──
if args.output_format == "excel":
    from exporters.excel_exporter import ExcelExporter

    # 견적서 프리셋: 표지 메타데이터 추출
    if preset == "estimate" and sections:
        cover_metadata = extract_cover_metadata(
            sections[0].get("clean_text", "")
        )
        print(f"   📋 표지 메타 추출 완료: {cover_metadata.get('serial_no', '(없음)')}")

    exporter = ExcelExporter()
    excel_path = out_dir / f"{date_str}_{input_stem}.xlsx"
    counter = 1
    while excel_path.exists():
        excel_path = out_dir / f"{date_str}_{input_stem}_{counter}.xlsx"
        counter += 1

    exporter.export(
        sections,
        excel_path,
        metadata=cover_metadata,
        preset_config=excel_config,
    )
    print(f"📊 Excel 출력: {excel_path}")
```

---

### 8. `requirements.txt` — 의존성 추가

```
# ── Phase 1 (기존) ──
pdfplumber
google-generativeai
pdf2image
Pillow
python-dotenv

# ── Phase 2 (기존) ──
beautifulsoup4        # HTML 테이블 파싱 (필수)
lxml                  # 고속 HTML 파서 (선택 — 미설치 시 html.parser 폴백)

# ── Phase 3 (신규) ──
openpyxl              # Excel 파일 생성 (.xlsx)
```

---

## 잠재 위험 요소 검토

### 위험 1: `_try_parse_number()` 위치 — Exporter vs Parser 경계

**문제:** Phase 2에서 `try_numeric()`을 의도적으로 제거(문자열 보존)했다. Phase 3에서 Excel 출력 시 숫자 변환이 필요한데, 이 로직을 어디에 둘 것인가?

**해결:** `exporters/excel_exporter.py`의 `_try_parse_number()` 정적 메서드로 배치.

| 계층 | 숫자 변환 여부 | 이유 |
|---|---|---|
| Phase 2 (parsers/) | ❌ 변환 안 함 | 원본 데이터 무결성 보호. JSON은 범용 중간 포맷. |
| Phase 3 (exporters/) | ✅ 변환 실행 | Excel은 최종 출력물. 숫자 셀이어야 SUM/정렬 가능. |

**선행 0 보호 규칙:**
- `"0015"` → 변환 안 함 (식별자 추정 → 문자열 유지)
- `"0"`, `"0.5"` → 변환 허용

**검증:**

| 입력 | `_try_parse_number()` 결과 | Excel 셀 타입 |
|---|---|---|
| `"15,000,000"` | `15000000` (int) | 숫자 (#,##0 포맷) |
| `"3.14"` | `3.14` (float) | 숫자 |
| `"0015"` | `None` | 문자열 |
| `"-"` | `None` | 문자열 |
| `""` | `None` | 빈 셀 |
| `"SUS304"` | `None` | 문자열 |
| `"PSQ26-0406-59"` | `None` | 문자열 |

---

### 위험 2: Excel 시트명 31자 제한

**문제:** 테이블 타이틀이나 파일명이 길면 Excel 시트명 31자 제한에 걸린다.

**해결:** `_safe_sheet_name()` 정적 메서드로 자동 truncate + 금칙 문자 제거.

---

### 위험 3: 테이블 자동 선택 오류 — 요약 vs 상세 혼동

**문제:** 견적서에는 요약 테이블(T-01: 8열)과 상세 테이블(T-03: 13열)이 공존한다. 행 수만으로 선택하면 부속 자료(장비 리스트, 규격표 등)를 내역서로 오인할 위험이 있다.

**해결 [v2 개선]:** `source_table_type` 필터 + **헤더 매칭 점수(Header Scoring)** + 행 수의 3단계 복합 스코어링.

```python
# 헤더 스코어링 키워드
HEADER_SCORE_KEYWORDS = {"품명", "규격", "단위", "수량", "단가", "금액", "합계", "명 칭"}

def _score(table: dict) -> tuple[int, int]:
    headers = set(table.get("headers", []))
    header_match = len(headers & HEADER_SCORE_KEYWORDS)  # 1차: 헤더 매칭
    row_count = table.get("parsed_row_count", 0)          # 2차: 행 수 (동점 시)
    return (header_match, row_count)

return max(all_tables, key=_score)
```

실제 데이터 기준:
- T-doc-01 (요약): 11행, type="A_품셈", 8열, 헤더매칭=4 (명칭/규격/단위/합계)
- T-doc-03 (상세): 19행, type="A_품셈", 13열, 헤더매칭=5 (명칭/규격/단위/금액/합계)
- (가정) 규격표: 50행, type="A_품셈", 6열, 헤더매칭=1 (규격만)

→ 헤더매칭 5점 > 4점 > 1점 → T-doc-03 선택 ✅ (행 수 50의 규격표 오선택 방지)

---

### 위험 4: `--preset estimate` + 파서 패턴 부재

**문제:** `estimate` 프리셋에는 `get_parse_patterns()`가 없다. Phase 2 파서에 `patterns=None`이 전달되면 도메인 메타데이터(notes, conditions 등)가 빈값이 된다.

**해결:** 이것은 **의도된 동작**이다.

| 프리셋 | Phase 2 patterns | Phase 2 type_keywords | Phase 3 excel_config |
|---|---|---|---|
| `pumsem` | PARSE_PATTERNS (8종) | TABLE_TYPE_KEYWORDS (4종) | 없음 (범용 Excel) |
| `estimate` | `None` (범용) | TABLE_TYPE_KEYWORDS (3종) | EXCEL_SHEET_CONFIG |
| 없음 (범용) | `None` | `None` | 없음 (범용 Excel) |

견적서는 `[주]` 블록이나 교차참조가 없으므로 파서 패턴이 불필요하다.
대신 `type_keywords`와 `excel_config`가 견적서 특화 기능을 담당한다.

---

### 위험 5: `.json` 직접 입력 시 BOM 인코딩

**문제:** Phase 2에서 `utf-8-sig`로 저장된 JSON을 다시 읽을 때 BOM이 중복될 수 있다.

**해결:** `open(input_path, "r", encoding="utf-8-sig")`로 읽으면 BOM이 자동으로 제거된다.
`utf-8-sig`는 읽기 시 BOM을 무시하고, 쓰기 시 BOM을 삽입하므로 양방향 안전.

---

### 위험 6: openpyxl 미설치 환경

**문제:** `--output excel` 사용 시에만 openpyxl이 필요한데, 기존 Phase 1/2 전용 사용자에게 불필요한 설치를 강요하게 된다.

**해결:** Lazy import 패턴 적용. `--output excel` 분기에서만 `from exporters.excel_exporter import ExcelExporter`를 실행. `--output md` 또는 `--output json`에서는 openpyxl을 import하지 않는다.

---

## 구현 순서 (의존성 기반)

```
1단계: 의존성 없는 모듈 (병렬 작업 가능)
  ├── exporters/__init__.py
  ├── exporters/base_exporter.py         (ABC 인터페이스)
  ├── presets/estimate.py                (견적서 프리셋 설정)
  ├── detector.py                        (문서 유형 감지)
  └── requirements.txt 업데이트           (openpyxl 추가)

2단계: Exporter 구현 (1단계 의존)
  ├── exporters/excel_exporter.py        (핵심 Excel 변환기)
  └── exporters/json_exporter.py         (JSON 저장 분리)

3단계: CLI 연결 (1+2단계 의존)
  └── main.py                            (--output excel, --preset estimate, .json 입력)
```

---

## 검증 계획

### 단위 테스트

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| `_try_parse_number` | `"15,000,000"`, `"0015"`, `"-"`, `""`, `"SUS304"` 5종 입력 | `15000000`, `None`, `None`, `None`, `None` |
| `_safe_sheet_name` | 32자 이상 + 금칙 문자 포함 문자열 입력 | 31자 이하, 금칙 문자 제거 |
| `_select_table` | 테이블 3개(type 혼합) + `source_table_type="A_품셈"`, `index=-1` | 가장 큰 A_품셈 테이블 |
| `extract_cover_metadata` | 견적서 clean_text 입력 | 6개 필드 정상 추출, amount=16700000 |
| `detect_document_type` | 견적서 PDF / 품셈 PDF / 일반 PDF | `"estimate"` / `"pumsem"` / `None` |

### 통합 테스트

| 검증 항목 | 명령어 | 기대 결과 |
|---|---|---|
| PDF→Excel (견적서) | `python main.py "견적서.pdf" --output excel --preset estimate` | 내역서+요약 2시트 Excel, 금액 열 숫자 포맷 |
| PDF→Excel (범용) | `python main.py "견적서.pdf" --output excel` | 테이블별 시트, 금액 열 숫자 포맷 |
| MD→Excel | `python main.py "output/추출.md" --output excel` | JSON 중간 거쳐 Excel 출력 |
| JSON→Excel | `python main.py "output/결과.json" --output excel` | JSON 직접 로드 → Excel 출력 |
| 문서 감지 | `python main.py "견적서.pdf" --output excel` (preset 미지정) | `💡 견적서로 감지...` 메시지 출력 |
| 기존 호환성 | `python main.py "견적서.pdf"` (--output 생략) | Phase 1 MD 출력 (변경 없음) |
| 기존 호환성 | `python main.py "추출.md" --output json --preset pumsem` | Phase 2 JSON 출력 (변경 없음) |

### 출력물 비교 테스트

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 금액 정합성 | Excel `내역서` 시트 합계 행 금액 vs JSON T-doc-03 합계 행 | 완전 일치 (15,188,655) |
| 열 수 일치 | Excel 열 수 vs JSON headers 배열 길이 | 13열 동일 |
| 행 수 일치 | Excel 데이터 행 수 vs JSON rows 배열 길이 | 19행 동일 |
| 파일 개수 | `--output excel` 실행 후 output/ 폴더 확인 | .xlsx 1개 (+ 중간 .md, .json은 PDF 입력 시에만) |

### 회귀 테스트 (Phase 1/2 기능 보존)

| 검증 항목 | 방법 | 기대 결과 |
|---|---|---|
| 기존 MD 추출 | `python main.py "견적서.pdf" --engine gemini` | Phase 1과 동일한 MD 출력 |
| 기존 JSON 변환 | `python main.py "추출.md" --output json --preset pumsem` | Phase 2와 동일한 JSON 출력 |
| text-only | `python main.py "견적서.pdf" --text-only` | Phase 1과 동일 |

---

## Phase 3 완료 후 파이프라인 전체 흐름

```
📄 입력 파일
     │
     ├── .pdf ─────────────────────────────────────────────────────
     │         │                                                   │
     │    [Phase 1: 추출]                                          │
     │    engines/ + extractors/                                   │
     │         │                                                   │
     │         ▼                                                   │
     │    📝 구조화 마크다운 (.md)                                   │
     │         │                                                   │
     ├── .md ──┤                                                   │
     │         │                                                   │
     │    [Phase 2: 정제]                                          │
     │    parsers/ + presets/                                      │
     │         │                                                   │
     │         ▼                                                   │
     │    📦 구조화 JSON (.json)                                    │
     │         │                                                   │
     ├── .json ┤                                                   │
     │         │                                                   │
     │    [Phase 3: 출력]           ← 이번 Phase                    │
     │    exporters/ + presets/                                    │
     │         │                                                   │
     │         ├── --output json  → 📦 JSON 파일                   │
     │         └── --output excel → 📊 Excel 파일 (.xlsx)          │
     │                                                             │
     └─────────────────────────────────────────────────────────────
```

---

> 작성일: 2026-04-13 | Phase 3 of 4 | 작성: Antigravity AI
