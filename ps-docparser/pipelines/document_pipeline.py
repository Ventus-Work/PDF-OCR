"""Document pipeline for generic, estimate, and pumsem documents."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pdfplumber

import config
from config import DEFAULT_ENGINE
from engines.factory import create_engine
from extractors.extraction_quality import evaluate_document_extraction
from pipelines.base import BasePipeline
from utils.io import ParserError, _safe_write_text
from utils.paths import get_output_path
from extractors import toc_parser as toc_parser_module


class DocumentPipeline(BasePipeline):
    """Integrated document pipeline for document / estimate / pumsem presets."""

    ALLOWED_ENGINES = frozenset({"gemini", "local", "zai", "mistral", "tesseract"})
    OCR_PRIMARY_ENGINES = frozenset({"zai", "mistral", "tesseract"})
    HYBRID_PRIMARY_ENGINES = frozenset({"gemini", "local"})
    PROMPTABLE_PRESETS = frozenset({"estimate"})

    def run(self) -> None:
        args = self.ctx.args
        input_path = self.ctx.input_path
        out_dir = self.ctx.output_dir
        preset = args.preset
        is_md_input = input_path.suffix.lower() == ".md"

        if is_md_input and args.output_format == "md":
            raise ParserError(
                ".md 파일 입력에서는 --output json/excel만 사용할 수 있습니다. "
                "--output md는 PDF -> MD 단계에서만 사용됩니다."
            )

        if getattr(args, "text_only", False) and args.output_format in ("json", "excel"):
            print("  [참고] --text-only + --output json/excel 조합: 텍스트 전용으로 추출 후 파싱합니다.")

        self._validate_engine(args.engine)
        preset_data = self._load_preset(preset)

        section_map = None
        md = None
        md_source = None
        detection_text = None
        page_indices = None

        if is_md_input:
            md_source = str(input_path)
            if args.output_format != "md":
                detection_text = input_path.read_text(encoding="utf-8")
        else:
            engine_name = args.engine or DEFAULT_ENGINE
            engine = self._build_engine(engine_name)

            with pdfplumber.open(str(input_path)) as pdf:
                total_pages = len(pdf.pages)

            if args.pages:
                from utils.page_spec import parse_page_spec

                page_indices = parse_page_spec(args.pages, total_pages)
                if not page_indices:
                    raise ParserError(
                        f"유효한 페이지가 없습니다: {args.pages} (총 {total_pages}페이지)"
                    )
                print(f"  페이지 지정: {args.pages} -> {len(page_indices)}페이지 처리 예정")

            if args.toc:
                from parsers.toc_loader import load_toc

                section_map = load_toc(args.toc)

            out_dir.mkdir(parents=True, exist_ok=True)
            md = self._extract_md(
                args=args,
                input_path=input_path,
                engine_name=engine_name,
                engine=engine,
                section_map=section_map,
                page_indices=page_indices,
                preset=preset,
                preset_data=preset_data,
            )
            detection_text = md

            if not md:
                raise ParserError("추출 결과가 없습니다.")

            md_path = get_output_path(
                out_dir,
                str(input_path),
                page_indices if args.pages else None,
            )
            _safe_write_text(md_path, md)
            print(f"  MD 출력: {md_path.name} ({len(md):,} bytes)")

            if args.output_format == "md":
                print("\n  완료!")
                if self.ctx.tracker and self.ctx.tracker.call_count > 0:
                    print(self.ctx.tracker.summary())
                return

            md_source = str(md_path)

        if preset is None and args.output_format != "md":
            confirmed_preset = self._maybe_confirm_detected_preset(detection_text or "")
            if confirmed_preset is not None:
                preset = confirmed_preset
                args.preset = confirmed_preset
                preset_data = self._load_preset(confirmed_preset)

        print("\n  === Phase 2: 마크다운 -> JSON 파싱 시작 ===")
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

        date_str = datetime.now().strftime("%Y%m%d")
        json_path = out_dir / f"{date_str}_{input_path.stem}.json"
        counter = 1
        while json_path.exists():
            json_path = out_dir / f"{date_str}_{input_path.stem}_{counter}.json"
            counter += 1

        from exporters.json_exporter import JsonExporter

        JsonExporter().export(sections, json_path)
        print(f"  JSON 저장: {json_path.name}")
        tables_total = sum(len(section.get("tables", [])) for section in sections)
        print(f"  섹션 수: {len(sections)} / 테이블 수: {tables_total}")

        if preset is None and detection_text:
            from detector import suggest_preset

            suggestion = suggest_preset(detection_text)
            if suggestion:
                print(suggestion)

        if args.output_format == "excel":
            print("\n  === Phase 3: JSON -> Excel 변환 시작 ===")
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
                sections,
                xlsx_path,
                metadata=cover_metadata,
                preset_config=preset_data.get("excel_config"),
            )
            print(f"  Excel 출력: {xlsx_path.name}")

        print("\n  완료!")
        if self.ctx.tracker and self.ctx.tracker.call_count > 0:
            print(self.ctx.tracker.summary())

    def _validate_engine(self, engine_name: str | None) -> None:
        if getattr(self.ctx.args, "text_only", False):
            return
        name = engine_name or getattr(self.ctx.args, "engine", None) or DEFAULT_ENGINE
        if name not in self.ALLOWED_ENGINES:
            raise ParserError(f"문서 파이프라인에서 지원하지 않는 엔진입니다: {name}")

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
            print(f"  프리셋 활성화: {preset}")
        elif preset == "estimate":
            from presets.estimate import (
                get_excel_config,
                get_table_type_keywords as get_estimate_keywords,
            )

            data["type_keywords"] = get_estimate_keywords()
            data["excel_config"] = get_excel_config()
            print(f"  프리셋 활성화: {preset}")
        return data

    def _build_engine(self, engine_name: str):
        if getattr(self.ctx.args, "text_only", False):
            print("  모드: 텍스트 전용 (엔진 없음)")
            return None

        engine = create_engine(engine_name, self.ctx.tracker)
        if self.ctx.cache is not None:
            engine.cache = self.ctx.cache
        print(f"  엔진: {type(engine).__name__}")
        return engine

    def _arg_value(self, name: str, default=None):
        args_dict = getattr(self.ctx.args, "__dict__", None)
        if isinstance(args_dict, dict) and name in args_dict:
            return args_dict[name]
        return getattr(self.ctx.args, name, default)

    def _should_prompt_for_detected_preset(self) -> bool:
        if self._arg_value("_is_batch_mode", False):
            return False

        stdin = getattr(sys, "stdin", None)
        stdout = getattr(sys, "stdout", None)
        if stdin is None or stdout is None:
            return False

        stdin_isatty = getattr(stdin, "isatty", None)
        stdout_isatty = getattr(stdout, "isatty", None)
        if not callable(stdin_isatty) or not callable(stdout_isatty):
            return False

        return bool(stdin_isatty() and stdout_isatty())

    def _maybe_confirm_detected_preset(self, md_text: str) -> str | None:
        if not md_text or not self._should_prompt_for_detected_preset():
            return None

        from detector import detect_document_type

        detected = detect_document_type(md_text)
        if detected not in self.PROMPTABLE_PRESETS:
            return None

        print(f"\n  문서 성격이 '{detected}'로 보입니다.")
        print(f"     [Enter] {detected}로 실행 / [g] generic으로 계속 / [c] 취소")

        while True:
            choice = input("     선택: ").strip().lower()
            if choice in ("", "e", "est", "estimate"):
                print(f"     {detected} 프리셋으로 계속 진행합니다.")
                return detected
            if choice in ("g", "generic"):
                print("     generic 흐름으로 계속 진행합니다.")
                return None
            if choice in ("c", "cancel", "q", "quit"):
                raise ParserError("사용자 선택으로 실행을 중단했습니다.")
            print("     Enter / g / c 중 하나를 입력해 주세요.")

    def _expected_pages(self, input_path: Path, page_indices: list[int] | None) -> int:
        if page_indices:
            return len(page_indices)
        with pdfplumber.open(str(input_path)) as pdf:
            return len(pdf.pages)

    def _run_extraction_with_engine(
        self,
        engine_name: str,
        engine,
        input_path: Path,
        section_map: dict | None,
        page_indices: list[int] | None,
        preset: str | None,
        division_names,
    ) -> str:
        if engine_name in self.OCR_PRIMARY_ENGINES:
            from extractors.ocr_document_extractor import process_pdf_ocr_document

            return process_pdf_ocr_document(
                str(input_path),
                engine=engine,
                section_map=section_map,
                page_indices=page_indices,
                toc_parser_module=toc_parser_module if section_map else None,
                preset=preset,
                division_names=division_names,
            )

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

    @staticmethod
    def _format_metrics(metrics) -> str:
        table_signal = metrics.html_table_count + metrics.markdown_table_blocks
        return (
            f"visible_chars={metrics.visible_chars}, "
            f"table_count={table_signal}, score={metrics.score}"
        )

    def _extract_md(
        self,
        args,
        input_path: Path,
        engine_name: str,
        engine,
        section_map: dict | None,
        page_indices: list[int] | None,
        preset: str | None,
        preset_data: dict,
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

        if engine_name in self.OCR_PRIMARY_ENGINES:
            return self._run_extraction_with_engine(
                engine_name=engine_name,
                engine=engine,
                input_path=input_path,
                section_map=section_map,
                page_indices=page_indices,
                preset=preset,
                division_names=division_names,
            )

        primary_md = self._run_extraction_with_engine(
            engine_name=engine_name,
            engine=engine,
            input_path=input_path,
            section_map=section_map,
            page_indices=page_indices,
            preset=preset,
            division_names=division_names,
        )

        expected_pages = self._expected_pages(input_path, page_indices)
        primary_metrics = evaluate_document_extraction(primary_md, expected_pages=expected_pages)
        if not primary_metrics.too_weak:
            return primary_md

        print(
            f"  1차 {engine_name} 결과 빈약({self._format_metrics(primary_metrics)})"
        )

        best_name = engine_name
        best_md = primary_md
        best_metrics = primary_metrics

        for fallback_name in config.DOCUMENT_OCR_FALLBACK_ORDER:
            if fallback_name == engine_name:
                continue

            try:
                fallback_engine = self._build_engine(fallback_name)
            except Exception as exc:
                print(f"    OCR fallback: {fallback_name} 건너뜀 ({exc})")
                continue

            print(f"    OCR fallback: {fallback_name} 시도")
            try:
                fallback_md = self._run_extraction_with_engine(
                    engine_name=fallback_name,
                    engine=fallback_engine,
                    input_path=input_path,
                    section_map=section_map,
                    page_indices=page_indices,
                    preset=preset,
                    division_names=division_names,
                )
            except Exception as exc:
                print(f"    OCR fallback: {fallback_name} 실패 ({exc})")
                continue
            fallback_metrics = evaluate_document_extraction(
                fallback_md,
                expected_pages=expected_pages,
            )

            if not fallback_metrics.too_weak:
                print(
                    f"    OCR fallback: {fallback_name} 채택 "
                    f"({self._format_metrics(fallback_metrics)})"
                )
                return fallback_md

            print(
                f"    OCR fallback: {fallback_name}도 빈약 "
                f"({self._format_metrics(fallback_metrics)})"
            )
            if fallback_metrics.score > best_metrics.score:
                best_name = fallback_name
                best_md = fallback_md
                best_metrics = fallback_metrics

        if best_name != engine_name and best_metrics.score > primary_metrics.score:
            print(
                f"  모든 fallback이 약했지만 최고 점수 결과를 채택합니다: "
                f"{best_name} ({self._format_metrics(best_metrics)})"
            )
            return best_md

        print(f"  fallback 채택 조건을 못 넘어서 1차 {engine_name} 결과를 유지합니다.")
        return primary_md
