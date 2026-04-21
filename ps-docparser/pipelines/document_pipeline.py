"""표준 문서 파이프라인 (pumsem/estimate/범용). (main.py L420-595 이식)"""

from datetime import datetime
from pathlib import Path

import config
from config import DEFAULT_ENGINE, GEMINI_API_KEY, GEMINI_MODEL
from engines.factory import create_engine
from pipelines.base import BasePipeline
from utils.io import ParserError, _safe_write_text
from utils.paths import get_output_path
from extractors import toc_parser as toc_parser_module


class DocumentPipeline(BasePipeline):
    """pumsem / estimate / 범용 통합 파이프라인."""

    ALLOWED_ENGINES = frozenset({"gemini", "local"})

    def run(self) -> None:
        args = self.ctx.args
        input_path = self.ctx.input_path
        out_dir = self.ctx.output_dir
        preset = args.preset
        is_md_input = input_path.suffix.lower() == ".md"

        # 0-a. .md 입력 + --output md 조합 금지 (Phase 1 전용 옵션)
        if is_md_input and args.output_format == "md":
            raise ParserError(
                ".md 파일 입력 시 --output json 을 사용하세요. "
                "--output md 는 Phase 1(PDF→MD) 전용입니다."
            )

        # 0-b. --text-only + json/excel 안내
        if getattr(args, "text_only", False) and args.output_format in ("json", "excel"):
            print("  [참고] --text-only와 --output json/excel 병용: "
                  "텍스트 전용으로 추출한 뒤 파싱합니다.")

        # 0-c. 엔진 제약 검증
        self._validate_engine(args.engine)

        # 1. 프리셋 리소스 로딩
        preset_data = self._load_preset(preset)

        # ── .md 직접 입력 vs PDF 입력 분기 ──
        section_map = None
        md = None
        md_source = None
        page_indices = None

        if is_md_input:
            md_source = str(input_path)
        else:
            engine_name = args.engine or DEFAULT_ENGINE
            engine = self._build_engine(engine_name, args)

            # 페이지 범위 파싱
            import pdfplumber
            with pdfplumber.open(str(input_path)) as pdf:
                total_pages = len(pdf.pages)

            if args.pages:
                from utils.page_spec import parse_page_spec
                page_indices = parse_page_spec(args.pages, total_pages)
                if not page_indices:
                    raise ParserError(
                        f"유효한 페이지가 없습니다: {args.pages} (총 {total_pages}페이지)"
                    )
                print(f"  페이지 지정: {args.pages} → {len(page_indices)}페이지 처리 예정")

            # 목차 로딩
            if args.toc:
                from parsers.toc_loader import load_toc
                section_map = load_toc(args.toc)

            # Phase 1: PDF → MD
            out_dir.mkdir(parents=True, exist_ok=True)
            md = self._extract_md(
                args, input_path, engine, section_map, page_indices,
                preset, preset_data,
            )

            if not md:
                raise ParserError("추출 결과가 없습니다.")

            md_path = get_output_path(out_dir, str(input_path), page_indices if args.pages else None)
            _safe_write_text(md_path, md)
            print(f"  MD 출력: {md_path.name} ({len(md):,} bytes)")

            if args.output_format == "md":
                print("\n  완료!")
                if self.ctx.tracker and self.ctx.tracker.call_count > 0:
                    print(self.ctx.tracker.summary())
                return

            md_source = str(md_path)

        # Phase 2: MD → JSON
        print("\n  ── Phase 2: 마크다운 → JSON 파싱 시작 ──")
        from parsers.document_parser import parse_markdown

        toc_path_for_parser = args.toc if args.toc and args.toc.endswith(".json") else None
        parse_target = md if md is not None else md_source
        sections = parse_markdown(
            parse_target,
            toc_path=toc_path_for_parser,
            type_keywords=preset_data.get("type_keywords"),
            patterns=preset_data.get("parse_patterns"),
        )
        print(f"  파싱 완료: {len(sections)}개 섹션")

        # JSON 저장
        date_str = datetime.now().strftime("%Y%m%d")
        json_path = out_dir / f"{date_str}_{input_path.stem}.json"
        counter = 1
        while json_path.exists():
            json_path = out_dir / f"{date_str}_{input_path.stem}_{counter}.json"
            counter += 1

        from exporters.json_exporter import JsonExporter
        JsonExporter().export(sections, json_path)
        print(f"  JSON 저장: {json_path.name}")
        tables_total = sum(len(s.get("tables", [])) for s in sections)
        print(f"  섹션 수: {len(sections)}  /  테이블 수: {tables_total}")

        if preset is None and md:
            from detector import suggest_preset
            suggestion = suggest_preset(md)
            if suggestion:
                print(suggestion)

        # Phase 3: JSON → Excel
        if args.output_format == "excel":
            print("\n  ── Phase 3: JSON → Excel 변환 시작 ──")
            from exporters.excel_exporter import ExcelExporter

            xlsx_path = out_dir / f"{date_str}_{input_path.stem}.xlsx"
            xlsx_counter = 1
            while xlsx_path.exists():
                xlsx_path = out_dir / f"{date_str}_{input_path.stem}_{xlsx_counter}.xlsx"
                xlsx_counter += 1

            cover_metadata = None
            if preset == "estimate" and sections:
                from presets.estimate import extract_cover_metadata
                cover_metadata = extract_cover_metadata(sections[0].get("clean_text", ""))
                print(f"     표지 메타 추출: {cover_metadata.get('serial_no', '(없음)')}")

            ExcelExporter().export(
                sections, xlsx_path,
                metadata=cover_metadata,
                preset_config=preset_data.get("excel_config"),
            )
            print(f"  Excel 출력: {xlsx_path.name}")

        print("\n  완료!")
        if self.ctx.tracker and self.ctx.tracker.call_count > 0:
            print(self.ctx.tracker.summary())

    # ── 내부 헬퍼 ──

    def _validate_engine(self, engine_name: str | None) -> None:
        """표준 파이프라인은 gemini/local만 허용."""
        if getattr(self.ctx.args, "text_only", False):
            return
        name = engine_name or getattr(self.ctx.args, "engine", None) or DEFAULT_ENGINE
        if name not in self.ALLOWED_ENGINES:
            raise ParserError(
                f"표준 파이프라인에서 지원하지 않는 엔진: {name}. "
                f"BOM 전용 엔진(zai/mistral/tesseract)은 --preset bom과 함께 사용하세요."
            )

    def _load_preset(self, preset: str | None) -> dict:
        data: dict = {}
        if preset == "pumsem":
            from presets.pumsem import (
                get_division_names,
                get_parse_patterns,
                get_table_type_keywords,
            )
            data["division_names"] = get_division_names()
            data["parse_patterns"] = get_parse_patterns()
            data["type_keywords"] = get_table_type_keywords()
            print(f"  프리셋 활성화: {preset} (부문명·파서 패턴·테이블 키워드 로드 완료)")
        elif preset == "estimate":
            from presets.estimate import (
                get_table_type_keywords as _get_est_keywords,
                get_excel_config,
            )
            data["type_keywords"] = _get_est_keywords()
            data["excel_config"] = get_excel_config()
            print(f"  프리셋 활성화: {preset} (테이블 키워드 + Excel 시트 구성 로드 완료)")
        return data

    def _build_engine(self, engine_name: str, args):
        if args.text_only:
            print("  모드: 텍스트 전용 (엔진 없음)")
            return None
        engine = create_engine(engine_name, self.ctx.tracker)
        print(f"  엔진: {type(engine).__name__}")
        return engine

    def _extract_md(
        self, args, input_path, engine, section_map, page_indices, preset, preset_data
    ) -> str:
        division_names = preset_data.get("division_names")
        if args.text_only:
            from extractors.text_extractor import process_pdf_text_only
            return process_pdf_text_only(
                str(input_path),
                section_map=section_map,
                page_indices=page_indices,
                toc_parser_module=toc_parser_module if section_map else None,
                preset=preset,
                division_names=division_names,
            )
        else:
            from extractors.hybrid_extractor import process_pdf
            return process_pdf(
                str(input_path),
                engine=engine,
                section_map=section_map,
                page_indices=page_indices,
                toc_parser_module=toc_parser_module if section_map else None,
                preset=preset,
                division_names=division_names,
            )
