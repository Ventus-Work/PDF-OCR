"""BOM 전용 파이프라인. (main.py L348-418 이식)

단일 PDF 1건만 처리한다.
배치 집계(export_aggregated_excel)는 호출자(main.py)가 담당한다.
"""

from pathlib import Path

import config
from engines.factory import create_engine
from pipelines.base import BasePipeline, PipelineContext
from utils.io import ParserError, _safe_write_text


class BomPipeline(BasePipeline):
    """OCR → BOM 구조화 → JSON/Excel 출력."""

    # gemini는 이미지 Vision이나 BOM 도면 전용이 아님. local은 OCR 미지원.
    ALLOWED_ENGINES = frozenset({"zai", "mistral", "tesseract", "local"})

    def run(self) -> None:
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

        from exporters.json_exporter import JsonExporter
        json_path = Path(str(output_base) + ".json")
        JsonExporter().export(sections, json_path)
        print(f"     JSON: {json_path.name}")

        if self.ctx.args.output_format == "excel":
            print(f"\n  {'='*50}")
            print("  Phase 3: Excel 출력")
            print(f"  {'='*50}")
            from exporters.excel_exporter import ExcelExporter
            xlsx_path = Path(str(output_base) + ".xlsx")
            ExcelExporter().export(sections, xlsx_path)
            print(f"     Excel: {xlsx_path.name}")

        print(f"\n  {'='*50}")
        print("  BOM 추출 완료!")
        print(f"  {'='*50}")
