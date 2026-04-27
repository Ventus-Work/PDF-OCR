"""BOM 전용 파이프라인. (main.py L348-418 이식)

단일 PDF 1건만 처리한다.
배치 집계(export_aggregated_excel)는 호출자(main.py)가 담당한다.
"""

from pathlib import Path

import config
from detector import detect_material_quote
from engines.factory import create_engine
from pipelines.base import BasePipeline, PipelineContext
from utils.io import ParserError, _safe_write_text

_ESTIMATE_OCR_CORRECTIONS = (
    ("HD현대오일백크", "HD현대오일뱅크"),
    ("오일백크", "오일뱅크"),
    ("건적금액", "견적금액"),
    ("건적일", "견적일"),
    ("건적", "견적"),
    ("결적유효기간", "견적유효기간"),
    ("결적 담당자", "견적 담당자"),
    ("결적 외", "견적 외"),
    ("결적", "견적"),
    ("신급금", "선급금"),
    ("충합계", "총합계"),
    ("적절비", "직접비"),
    ("물랑 산초丑", "물량 산출표"),
)


def _apply_estimate_ocr_corrections(text: str) -> str:
    """Apply conservative estimate-domain OCR corrections."""

    corrected = text
    for source, target in _ESTIMATE_OCR_CORRECTIONS:
        corrected = corrected.replace(source, target)
    return corrected


class BomPipeline(BasePipeline):
    """OCR → BOM 구조화 → JSON/Excel 출력."""

    # gemini는 이미지 Vision이나 BOM 도면 전용이 아님. local은 OCR 미지원.
    ALLOWED_ENGINES = frozenset({"zai", "mistral", "tesseract", "local"})

    def _resolve_fallback_mode(self) -> str:
        if getattr(self.ctx.args, "no_bom_fallback", False):
            return "never"
        mode = getattr(self.ctx.args, "bom_fallback", "auto")
        if mode not in {"auto", "always", "never"}:
            return "auto"
        return mode

    def _has_strong_primary_package(self, bom_result) -> bool:
        bom_sections = getattr(bom_result, "bom_sections", []) or []
        line_list_sections = getattr(bom_result, "line_list_sections", []) or []
        has_bom_rows = any(getattr(section, "rows", []) for section in bom_sections)
        has_line_list_rows = any(getattr(section, "rows", []) for section in line_list_sections)
        if not (has_bom_rows and has_line_list_rows):
            return False

        core_tokens = ("S/N", "SIZE", "MAT", "QTY", "Q'TY", "WT", "WEIGHT", "DESCRIPTION")
        for section in bom_sections:
            header_text = " ".join(str(header).upper() for header in getattr(section, "headers", []) or [])
            hits = sum(1 for token in core_tokens if token in header_text)
            if hits >= 3:
                return True
        return False

    def _evaluate_fallback_signals(self, bom_result) -> tuple[bool, bool]:
        raw_text = getattr(bom_result, "raw_text", "") or ""
        raw_text_len = len(raw_text.strip())
        drawing_metadata = getattr(bom_result, "drawing_metadata", {}) or {}
        if not isinstance(drawing_metadata, dict):
            drawing_metadata = {}
        has_meta = any(v is not None for v in drawing_metadata.values())
        total_tables = len(getattr(bom_result, "bom_sections", []) or []) + len(
            getattr(bom_result, "line_list_sections", []) or []
        )
        strong_primary_package = self._has_strong_primary_package(bom_result)

        looks_like_mixed_doc = (
            0 < total_tables <= 2
            and not has_meta
            and raw_text_len >= 1000
            and not strong_primary_package
        )
        looks_like_material_quote = (
            total_tables == 0
            and raw_text_len >= 500
            and detect_material_quote(raw_text)
        )
        return looks_like_mixed_doc, looks_like_material_quote

    def _run_estimate_fallback(
        self,
        *,
        engine_name: str,
        page_indices: list[int] | None,
        output_base: Path,
        reason: str,
    ) -> dict | None:
        import logging

        logger = logging.getLogger(__name__)
        print("     자동 폴백: estimate 프리셋 재실행")
        logger.warning("BOM auto fallback triggered: %s", reason)

        try:
            fallback_engine = create_engine(engine_name, self.ctx.tracker)
            if self.ctx.cache is not None:
                fallback_engine.cache = self.ctx.cache

            from extractors.ocr_document_extractor import process_pdf_ocr_document
            from exporters.json_exporter import JsonExporter
            from parsers.document_parser import parse_markdown
            from presets.estimate import (
                extract_cover_metadata,
                get_excel_config,
                get_table_type_keywords,
            )

            fallback_md = process_pdf_ocr_document(
                str(self.ctx.input_path),
                engine=fallback_engine,
                page_indices=page_indices,
                preset="estimate",
            )
            fallback_md = _apply_estimate_ocr_corrections(fallback_md)

            fallback_base = Path(str(output_base) + "_fallback_estimate")
            fallback_md_path = Path(str(fallback_base) + ".md")
            _safe_write_text(fallback_md_path, fallback_md, encoding="utf-8")
            print(f"     Fallback MD: {fallback_md_path.name}")

            sections = parse_markdown(
                fallback_md,
                type_keywords=get_table_type_keywords(),
            )
            from validators.output_quality import annotate_output_contract
            from utils.run_manifest import quality_status_from_sections

            sections = annotate_output_contract(sections, preset="estimate")
            fallback_quality_status = quality_status_from_sections(sections)

            fallback_json_path = Path(str(fallback_base) + ".json")
            JsonExporter().export(sections, fallback_json_path)
            print(f"     Fallback JSON: {fallback_json_path.name}")

            if self.ctx.args.output_format == "excel":
                from exporters.excel_exporter import ExcelExporter

                cover_metadata = None
                if sections:
                    cover_metadata = extract_cover_metadata(
                        sections[0].get("clean_text", "")
                    )

                fallback_xlsx_path = Path(str(fallback_base) + ".xlsx")
                ExcelExporter().export(
                    sections,
                    fallback_xlsx_path,
                    metadata=cover_metadata,
                    preset_config=get_excel_config(),
                )
                print(f"     Fallback Excel: {fallback_xlsx_path.name}")
            else:
                fallback_xlsx_path = None

            return {
                "md": fallback_md_path,
                "json": fallback_json_path,
                "xlsx": fallback_xlsx_path,
                "reason": reason,
                "quality_status": fallback_quality_status,
            }
        except Exception as exc:
            logger.warning("BOM auto fallback failed: %s", exc)
            print(f"     자동 폴백 실패: {exc}")
            return None

    def run(self) -> dict:
        from presets.bom import get_bom_keywords, get_image_settings
        bom_keywords = get_bom_keywords()
        image_settings = get_image_settings()

        engine_name = self.ctx.args.engine or config.BOM_DEFAULT_ENGINE
        print(f"  프리셋: bom (엔진: {engine_name})")

        bom_engine = create_engine(engine_name, self.ctx.tracker)
        if not bom_engine.supports_ocr:
            raise ParserError(
                f"BOM 프리셋은 OCR 엔진(zai/mistral/tesseract)이 필요합니다. "
                f"현재: {engine_name} → --engine zai 로 변경하세요."
            )

        if self.ctx.cache is not None:
            bom_engine.cache = self.ctx.cache

        self.ctx.output_dir.mkdir(parents=True, exist_ok=True)
        output_base = self._get_output_base("_bom")

        page_indices = self._resolve_pages()

        print(f"\n  {'='*50}")
        print(f"  Phase 1-BOM: OCR 추출 (엔진: {engine_name})")
        print(f"  {'='*50}")

        from extractors.bom_extractor import extract_bom_with_retry, to_sections
        bom_result = extract_bom_with_retry(
            bom_engine, self.ctx.input_path, bom_keywords, image_settings, page_indices
        )

        md_path = Path(str(output_base) + ".md")
        _safe_write_text(md_path, bom_result.raw_text, encoding="utf-8")
        print(f"     OCR 원문: {md_path.name}")

        print(f"\n  {'='*50}")
        print("  Phase 2-BOM: BOM 데이터 구조화")
        print(f"  {'='*50}")

        sections = to_sections(bom_result)
        print(f"     BOM {len(bom_result.bom_sections)}개 / "
              f"LINE LIST {len(bom_result.line_list_sections)}개")

        # [P4] 혼합 문서 경고 로그 추가
        looks_like_mixed_doc, looks_like_material_quote = self._evaluate_fallback_signals(
            bom_result
        )
        fallback_mode = self._resolve_fallback_mode()

        manifest_warnings = []
        if looks_like_material_quote:
            import logging
            logger = logging.getLogger(__name__)
            warning_msg = (
                "비-BOM 자재 견적표로 보입니다. 현재 문서는 BOM 구조가 아니라 "
                "document/generic 경로가 더 적합합니다. --preset bom 대신 기본 경로로 다시 실행해보세요."
            )
            print(f"     {warning_msg}")
            logger.warning(warning_msg)
            manifest_warnings.append("material_quote")
        
        if looks_like_mixed_doc:
            import logging
            logger = logging.getLogger(__name__)
            warning_msg = "⚠ 혼합 문서(견적/내역서+BOM 표 1~2개)로 추정됩니다. 도면 메타데이터가 없고 텍스트가 많아 일부 테이블만 추출되었을 수 있습니다."
            print(f"     {warning_msg}")
            logger.warning(warning_msg)
            manifest_warnings.append("mixed_document")

        from exporters.json_exporter import JsonExporter
        from validators.output_quality import annotate_output_contract

        sections = annotate_output_contract(sections, preset="bom")
        json_path = Path(str(output_base) + ".json")
        JsonExporter().export(sections, json_path)
        print(f"     JSON: {json_path.name}")

        xlsx_path = None
        if self.ctx.args.output_format == "excel":
            print(f"\n  {'='*50}")
            print("  Phase 3: Excel 출력")
            print(f"  {'='*50}")
            from exporters.excel_exporter import ExcelExporter
            xlsx_path = Path(str(output_base) + ".xlsx")
            ExcelExporter().export(sections, xlsx_path)
            print(f"     Excel: {xlsx_path.name}")

        fallback_reason = None
        fallback_artifact = None
        if looks_like_material_quote:
            fallback_reason = "material_quote"
        elif looks_like_mixed_doc:
            fallback_reason = "mixed_document"
        elif fallback_mode == "always":
            fallback_reason = "forced"

        if fallback_reason and fallback_mode == "never":
            print("     자동 폴백 비활성화(--bom-fallback never)")

        if fallback_reason and fallback_mode != "never":
            fallback_artifact = self._run_estimate_fallback(
                engine_name=engine_name,
                page_indices=page_indices,
                output_base=output_base,
                reason=fallback_reason,
            )

        from utils.run_manifest import (
            make_artifact,
            quality_status_from_sections,
            record_manifest_entry,
        )

        quality_status = quality_status_from_sections(sections)
        diagnostics = []
        if fallback_artifact:
            fallback_role = "representative" if fallback_artifact.get("reason") == "mixed_document" else "diagnostic"
            diagnostics.append(
                make_artifact(
                    output_dir=self.ctx.output_dir,
                    role=fallback_role,
                    domain="estimate",
                    md_path=fallback_artifact.get("md"),
                    json_path=fallback_artifact.get("json"),
                    xlsx_path=fallback_artifact.get("xlsx"),
                    quality_status=str(fallback_artifact.get("quality_status") or "warning"),
                    kind="fallback_estimate",
                )
            )

        entry = {
            "source_pdf": self.ctx.input_path.name,
            "preset": "bom",
            "engine": engine_name,
            "status": "success",
            "fallback_mode": fallback_mode,
            "warnings": manifest_warnings,
            "primary": make_artifact(
                output_dir=self.ctx.output_dir,
                role="representative",
                domain="bom",
                md_path=md_path,
                json_path=json_path,
                xlsx_path=xlsx_path,
                quality_status=quality_status,
                kind="primary",
            ),
            "diagnostics": diagnostics,
        }
        record_manifest_entry(self.ctx.output_dir, entry)

        print(f"\n  {'='*50}")
        print("  BOM 추출 완료!")
        print(f"  {'='*50}")
        return entry
