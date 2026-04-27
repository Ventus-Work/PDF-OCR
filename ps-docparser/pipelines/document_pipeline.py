"""Document pipeline for generic, estimate, pumsem, and auto-routing flows."""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from pathlib import Path
import json
import sys

import pdfplumber

import config
from config import DEFAULT_ENGINE
from detector import DetectionResult, analyze_document_type
from engines.factory import create_engine
from extractors import toc_parser as toc_parser_module
from extractors.extraction_quality import evaluate_document_extraction
from pipelines.base import BasePipeline, PipelineContext
from utils.io import ParserError, _safe_write_text
from utils.paths import get_compare_dir, get_output_base_name


@dataclass(frozen=True)
class RoutingDecision:
    """Normalized routing decision used by DocumentPipeline.run()."""

    mode: str
    target_preset: str | None
    save_compare: bool
    needs_confirmation: bool
    reason: str


class DocumentPipeline(BasePipeline):
    """Integrated document pipeline for document / estimate / pumsem presets."""

    ALLOWED_ENGINES = frozenset({"gemini", "local", "zai", "mistral", "tesseract"})
    OCR_PRIMARY_ENGINES = frozenset({"zai", "mistral", "tesseract"})
    HYBRID_PRIMARY_ENGINES = frozenset({"gemini", "local"})
    ROUTABLE_PRESETS = frozenset({"estimate", "pumsem", "bom"})

    def run(self) -> None:
        args = self.ctx.args
        input_path = self.ctx.input_path
        out_dir = self.ctx.output_dir
        explicit_preset = args.preset
        is_md_input = input_path.suffix.lower() == ".md"

        if is_md_input and args.output_format == "md":
            raise ParserError(
                ".md 파일 입력에서는 --output json/excel만 사용할 수 있습니다. "
                "--output md는 PDF -> MD 단계에서만 사용합니다."
            )

        if getattr(args, "text_only", False) and args.output_format in ("json", "excel"):
            print("  [참고] --text-only + --output json/excel 조합: 텍스트 전용으로 추출 후 파싱합니다.")

        self._validate_engine(args.engine)
        preset_data = self._load_preset(explicit_preset)

        page_indices = None
        section_map = None
        md_text = None

        if is_md_input:
            md_text = input_path.read_text(encoding="utf-8")
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
                print(f"  페이지 지정 {args.pages} -> {len(page_indices)}페이지 처리 예정")

            if args.toc:
                from parsers.toc_loader import load_toc

                section_map = load_toc(args.toc)

            out_dir.mkdir(parents=True, exist_ok=True)
            md_text = self._extract_md(
                args=args,
                input_path=input_path,
                engine_name=engine_name,
                engine=engine,
                section_map=section_map,
                page_indices=page_indices,
                preset=explicit_preset,
                preset_data=preset_data,
            )

        if not md_text:
            raise ParserError("추출 결과가 없습니다.")

        if args.output_format == "md":
            bundle = self._export_generic_bundle(
                md_text=md_text,
                input_path=input_path,
                output_dir=out_dir,
                page_indices=page_indices,
                output_format="md",
                preset_data=preset_data,
                preset=explicit_preset,
                write_md=not is_md_input,
                print_summary=True,
            )
            if bundle["paths"].get("md"):
                print(f"  MD 출력: {Path(bundle['paths']['md']).name} ({len(md_text):,} bytes)")
            print("\n  완료!")
            if self.ctx.tracker and self.ctx.tracker.call_count > 0:
                print(self.ctx.tracker.summary())
            return

        if explicit_preset is not None:
            self._export_generic_bundle(
                md_text=md_text,
                input_path=input_path,
                output_dir=out_dir,
                page_indices=page_indices,
                output_format=args.output_format,
                preset_data=preset_data,
                preset=explicit_preset,
                write_md=not is_md_input,
                print_summary=True,
            )
            print("\n  완료!")
            if self.ctx.tracker and self.ctx.tracker.call_count > 0:
                print(self.ctx.tracker.summary())
            return

        result = self._analyze_routing(md_text)
        decision = self._resolve_routing_decision(result)
        decision = self._confirm_route_if_needed(decision)

        if decision.mode == "generic":
            self._export_generic_bundle(
                md_text=md_text,
                input_path=input_path,
                output_dir=out_dir,
                page_indices=page_indices,
                output_format=args.output_format,
                preset_data={},
                preset=None,
                write_md=not is_md_input,
                print_summary=True,
            )
            if result.suggestion:
                print(result.suggestion)
        elif decision.target_preset in {"estimate", "pumsem"}:
            print(f"  자동 감지: {decision.reason}")
            compare_paths = self._export_compare_bundle(
                md_text=md_text,
                input_path=input_path,
                output_dir=out_dir,
                page_indices=page_indices,
                output_format=args.output_format,
            )
            final_paths = self._run_specialized_on_existing_md(
                md_text=md_text,
                input_path=input_path,
                output_dir=out_dir,
                page_indices=page_indices,
                output_format=args.output_format,
                target_preset=decision.target_preset,
                write_md=not is_md_input,
            )
            self._write_route_manifest(
                input_path=input_path,
                compare_paths=compare_paths,
                final_paths=final_paths,
                result=result,
                decision=decision,
            )
        elif decision.target_preset == "bom":
            print(f"  자동 감지: {decision.reason}")
            compare_paths = self._export_compare_bundle(
                md_text=md_text,
                input_path=input_path,
                output_dir=out_dir,
                page_indices=page_indices,
                output_format=args.output_format,
            )
            final_paths = self._run_bom_specialized()
            self._write_route_manifest(
                input_path=input_path,
                compare_paths=compare_paths,
                final_paths=final_paths,
                result=result,
                decision=decision,
            )
        else:
            raise ParserError(f"알 수 없는 라우팅 상태입니다: {decision}")

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

    def _analyze_routing(self, md_text: str) -> DetectionResult:
        return analyze_document_type(md_text)

    def _resolve_routing_decision(self, result: DetectionResult) -> RoutingDecision:
        if result.label not in self.ROUTABLE_PRESETS:
            return RoutingDecision(
                mode="generic",
                target_preset=None,
                save_compare=False,
                needs_confirmation=False,
                reason="generic",
            )

        if result.label == "bom" and self.ctx.input_path.suffix.lower() == ".md":
            return RoutingDecision(
                mode="generic",
                target_preset=None,
                save_compare=False,
                needs_confirmation=False,
                reason="bom auto-route requires original PDF input",
            )

        if result.confidence == "high":
            return RoutingDecision(
                mode="specialized",
                target_preset=result.label,
                save_compare=True,
                needs_confirmation=False,
                reason=f"{result.label} ({result.confidence})",
            )

        if result.confidence == "medium" and self._should_prompt_for_detected_preset():
            return RoutingDecision(
                mode="specialized",
                target_preset=result.label,
                save_compare=True,
                needs_confirmation=True,
                reason=f"{result.label} ({result.confidence})",
            )

        return RoutingDecision(
            mode="generic",
            target_preset=None,
            save_compare=False,
            needs_confirmation=False,
            reason="generic",
        )

    def _confirm_route_if_needed(self, decision: RoutingDecision) -> RoutingDecision:
        if not decision.needs_confirmation or not decision.target_preset:
            return decision

        preset = decision.target_preset
        print(f"\n  문서 성격 추정: {decision.reason}")
        print(f"     [Enter] {preset} 특화 / [g] generic / [c] 취소")

        while True:
            choice = input("     선택: ").strip().lower()
            if choice in ("", preset, preset[:3]):
                print(f"     {preset} 특화 경로로 계속 진행합니다.")
                return RoutingDecision(
                    mode="specialized",
                    target_preset=preset,
                    save_compare=True,
                    needs_confirmation=False,
                    reason=f"{preset} (medium, confirmed)",
                )
            if choice in ("g", "generic"):
                print("     generic 경로로 계속 진행합니다.")
                return RoutingDecision(
                    mode="generic",
                    target_preset=None,
                    save_compare=False,
                    needs_confirmation=False,
                    reason="generic",
                )
            if choice in ("c", "cancel", "q", "quit"):
                raise ParserError("사용자 선택으로 실행이 중단되었습니다.")
            print("     Enter / g / c 중 하나를 입력해 주세요.")

    def _reserve_bundle_base_name(
        self,
        *,
        output_dir: Path,
        input_path: Path,
        page_indices: list[int] | None,
        include_json: bool,
        include_md: bool,
        include_xlsx: bool,
    ) -> str:
        base_name = get_output_base_name(input_path, page_indices)
        counter = 0

        while True:
            suffix = "" if counter == 0 else f"_{counter}"
            candidate = f"{base_name}{suffix}"
            required_paths = []
            if include_json:
                required_paths.append(output_dir / f"{candidate}.json")
            if include_md:
                required_paths.append(output_dir / f"{candidate}.md")
            if include_xlsx:
                required_paths.append(output_dir / f"{candidate}.xlsx")
            if not any(path.exists() for path in required_paths):
                return candidate
            counter += 1

    def _parse_sections(
        self,
        md_text: str,
        preset_data: dict,
        *,
        preset: str | None = None,
    ) -> list[dict]:
        from parsers.document_parser import parse_markdown
        from validators.output_quality import annotate_output_contract

        args = self.ctx.args
        toc_path = args.toc if args.toc and args.toc.endswith(".json") else None
        print("\n  === Phase 2: 마크다운 -> JSON 파싱 시작 ===")
        sections = parse_markdown(
            md_text,
            toc_path=toc_path,
            type_keywords=preset_data.get("type_keywords"),
            patterns=preset_data.get("parse_patterns"),
        )
        sections = annotate_output_contract(sections, preset=preset)
        print(f"  파싱 완료: {len(sections)}개 섹션")
        return sections

    def _domain_from_sections(
        self,
        sections: list[dict],
        *,
        preset: str | None,
    ) -> str:
        if preset in {"estimate", "pumsem"}:
            return preset
        domains: list[str] = []
        for section in sections:
            if section.get("domain"):
                domains.append(str(section["domain"]))
            for table in section.get("tables", []) or []:
                if table.get("domain"):
                    domains.append(str(table["domain"]))
        unique_domains = set(domains)
        if len(unique_domains) == 1:
            return domains[0]
        return "generic"

    def _export_generic_bundle(
        self,
        *,
        md_text: str,
        input_path: Path,
        output_dir: Path,
        page_indices: list[int] | None,
        output_format: str,
        preset_data: dict,
        preset: str | None,
        write_md: bool,
        print_summary: bool,
        base_name: str | None = None,
        record_manifest: bool = True,
    ) -> dict:
        output_dir.mkdir(parents=True, exist_ok=True)

        if output_format == "md":
            include_xlsx = False
        else:
            include_xlsx = output_format == "excel"

        if base_name is None:
            base_name = self._reserve_bundle_base_name(
                output_dir=output_dir,
                input_path=input_path,
                page_indices=page_indices,
                include_json=output_format != "md",
                include_md=write_md,
                include_xlsx=include_xlsx,
            )

        md_path = output_dir / f"{base_name}.md" if write_md else None
        json_path = None
        xlsx_path = None

        if md_path is not None:
            _safe_write_text(md_path, md_text)

        if output_format == "md":
            return {
                "base_name": base_name,
                "paths": {"md": str(md_path) if md_path else None},
                "sections": [],
            }

        sections = self._parse_sections(md_text, preset_data, preset=preset)

        from exporters.json_exporter import JsonExporter

        json_path = output_dir / f"{base_name}.json"
        JsonExporter().export(sections, json_path)

        if print_summary:
            if md_path is not None:
                print(f"  MD 출력: {md_path.name} ({len(md_text):,} bytes)")
            print(f"  JSON 저장: {json_path.name}")
            tables_total = sum(len(section.get("tables", [])) for section in sections)
            print(f"  섹션 수: {len(sections)} / 테이블 수: {tables_total}")

        if output_format == "excel":
            print("\n  === Phase 3: JSON -> Excel 변환 시작 ===")
            from exporters.excel_exporter import ExcelExporter

            cover_metadata = None
            if preset == "estimate" and sections:
                from presets.estimate import extract_cover_metadata

                cover_metadata = extract_cover_metadata(sections[0].get("clean_text", ""))
                print(f"     표지 메타 추출: {cover_metadata.get('serial_no', '(없음)')}")

            xlsx_path = output_dir / f"{base_name}.xlsx"
            ExcelExporter().export(
                sections,
                xlsx_path,
                metadata=cover_metadata,
                preset_config=preset_data.get("excel_config"),
            )
            if print_summary:
                print(f"  Excel 출력: {xlsx_path.name}")

        if record_manifest:
            from utils.run_manifest import (
                make_artifact,
                quality_status_from_sections,
                record_manifest_entry,
            )

            domain = self._domain_from_sections(sections, preset=preset)
            quality_status = quality_status_from_sections(sections)
            record_manifest_entry(
                output_dir,
                {
                    "source_pdf": input_path.name,
                    "preset": preset or "generic",
                    "output_format": output_format,
                    "status": "success",
                    "primary": make_artifact(
                        output_dir=output_dir,
                        role="representative",
                        domain=domain,
                        md_path=md_path,
                        json_path=json_path,
                        xlsx_path=xlsx_path,
                        quality_status=quality_status,
                    ),
                    "diagnostics": [],
                },
            )

        return {
            "base_name": base_name,
            "paths": {
                "md": str(md_path) if md_path else None,
                "json": str(json_path) if json_path else None,
                "xlsx": str(xlsx_path) if xlsx_path else None,
            },
            "sections": sections,
        }

    def _export_compare_bundle(
        self,
        *,
        md_text: str,
        input_path: Path,
        output_dir: Path,
        page_indices: list[int] | None,
        output_format: str,
    ) -> dict:
        compare_dir = get_compare_dir(output_dir, input_path, page_indices)
        generic_dir = compare_dir / "generic"
        base_name = compare_dir.name

        print(f"  Compare baseline 저장: {generic_dir}")
        bundle = self._export_generic_bundle(
            md_text=md_text,
            input_path=input_path,
            output_dir=generic_dir,
            page_indices=page_indices,
            output_format=output_format,
            preset_data={},
            preset=None,
            write_md=True,
            print_summary=False,
            base_name=base_name,
            record_manifest=False,
        )
        bundle["compare_dir"] = str(compare_dir)
        return bundle

    def _write_route_manifest(
        self,
        *,
        input_path: Path,
        compare_paths: dict,
        final_paths: dict,
        result: DetectionResult,
        decision: RoutingDecision,
    ) -> None:
        compare_dir = Path(compare_paths["compare_dir"])
        compare_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = compare_dir / "route_manifest.json"

        payload = {
            "source_input": str(input_path),
            "detected_label": result.label,
            "confidence": result.confidence,
            "scores": result.scores,
            "reason_hits": result.reason_hits,
            "material_quote": result.material_quote,
            "chosen_mode": decision.mode,
            "target_preset": decision.target_preset,
            "interactive_confirmation": "confirmed" in decision.reason,
            "final_output_paths": final_paths.get("paths", {}),
            "compare_output_paths": compare_paths.get("paths", {}),
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Route manifest 저장: {manifest_path.name}")

    def _run_specialized_on_existing_md(
        self,
        *,
        md_text: str,
        input_path: Path,
        output_dir: Path,
        page_indices: list[int] | None,
        output_format: str,
        target_preset: str,
        write_md: bool,
    ) -> dict:
        preset_data = self._load_preset(target_preset)
        return self._export_generic_bundle(
            md_text=md_text,
            input_path=input_path,
            output_dir=output_dir,
            page_indices=page_indices,
            output_format=output_format,
            preset_data=preset_data,
            preset=target_preset,
            write_md=write_md,
            print_summary=True,
        )

    def _run_bom_specialized(self) -> dict:
        from pipelines.bom_pipeline import BomPipeline

        cloned_args = copy(self.ctx.args)
        cloned_args.preset = "bom"
        if getattr(cloned_args, "engine", None) not in BomPipeline.ALLOWED_ENGINES:
            cloned_args.engine = config.BOM_DEFAULT_ENGINE
        cloned_ctx = PipelineContext(
            input_path=self.ctx.input_path,
            output_dir=self.ctx.output_dir,
            args=cloned_args,
            cache=self.ctx.cache,
            tracker=self.ctx.tracker,
        )
        bom_pipeline = BomPipeline(cloned_ctx)
        output_base = bom_pipeline._get_output_base("_bom")
        bom_pipeline.run()
        return {
            "paths": {
                "md": str(Path(str(output_base) + ".md")),
                "json": str(Path(str(output_base) + ".json")),
                "xlsx": str(Path(str(output_base) + ".xlsx"))
                if self.ctx.args.output_format == "excel"
                else None,
            }
        }

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
                f"  모든 fallback이 실패했지만 최고 점수 결과를 채택합니다: "
                f"{best_name} ({self._format_metrics(best_metrics)})"
            )
            return best_md

        print(f"  fallback 채택 조건을 못 채워서 1차 {engine_name} 결과를 유지합니다.")
        return primary_md
