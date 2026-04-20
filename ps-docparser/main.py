"""
main.py — ps-docparser CLI 진입점

Why: 이 파일은 비즈니스 로직을 포함하지 않는다.
     각 모듈을 import하여 파이프라인을 조립하는 컨트롤러 역할만 한다.
     모든 설계 결정(엔진 선택, 프리셋, 출력 경로 등)을 CLI 인수로 받아
     아래 계층에 전달한다.

Phase 5 변경사항:
    - ParserError 예외 클래스 추가:
        sys.exit()를 전부 raise ParserError()로 전환하여
        배치 처리 중 단일 파일 오류가 전체 루프를 죽이지 않도록 방어.
    - _process_single() 분리:
        단일 파일 파이프라인을 독립 함수로 추출.
        main()은 파일/디렉토리 분기 + 캐시 생명주기만 관리한다.
    - 배치 처리 지원:
        입력이 디렉토리면 하위 PDF 파일 전체를 순차 처리.
        배치 진행 상황(n/total) 및 최종 성공/실패 요약 출력.
    - 캐시 주입:
        config.CACHE_ENABLED=true이면 TableCache 인스턴스를 생성하고
        OCR 엔진(bom_engine)에 주입. 동일 파일 재실행 시 API 재호출 없음.

흐름 (Phase 1: --output md):
    1. argparse로 CLI 인수 파싱
    2. config.py에서 전역 설정 로딩
    3. --preset에 따라 division_names 결정 (None = 범용)
    4. --engine에 따라 엔진 인스턴스 생성
    5. --text-only → text_extractor.process_pdf_text_only()
       아니면   → hybrid_extractor.process_pdf()
    6. output/ 폴더에 MD 파일 저장
    7. 사용량 summary 출력

흐름 (Phase 2: --output json):
    1~5. 동일 (PDF → MD 추출)  [.md 입력 시 1~4 스킵]
    6. parsers.document_parser.parse_markdown() → 섹션 JSON 리스트
    7. output/ 폴더에 JSON 파일 저장

흐름 (Phase 3: --output excel):
    1~6. 동일 (PDF/MD → JSON)
    7. exporters.excel_exporter.export() → .xlsx 파일 저장
       - 테이블 유형 자동 분류: 견적서 / 내역서 / 조건 시트

흐름 (Phase 4: --preset bom):
    BOM 전용 파이프라인 — OCR 엔진(zai/mistral/tesseract) 사용
    1. OCR 엔진으로 PDF 전체 인식
    2. BOM/LINE LIST 섹션 감지 및 구조화
    3. JSON + (옵션) Excel 출력

사용법:
    python main.py <PDF, .md 또는 디렉토리> [옵션]

옵션:
    --engine <이름>      AI 엔진 (gemini|local|zai|mistral|tesseract)
    --text-only, -t     텍스트 전용 모드 (AI 없음, 무료)
    --toc <파일>         목차 파일 (.json 또는 .txt)
    --pages <지정>       페이지 범위 (예: 1-15, 20-, 1,3,5-10)
    --output-dir <경로>  출력 폴더 (기본: ./output/)
    --preset <이름>      도메인 프리셋 (pumsem|estimate|bom, 기본: 없음=범용)
    --output <형식>      출력 형식 (md|json|excel, 기본: md)
"""

import os
import sys
import json
import platform
import argparse
from datetime import datetime
from pathlib import Path

# ── 프로젝트 루트를 sys.path에 추가 (어느 디렉토리에서 실행해도 import 가능) ──
# Why: main.py를 다른 경로에서 실행하면 패키지를 찾지 못한다.
#      __file__ 기준 절대 경로를 sys.path에 삽입하여 이식성 보장.
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import config
from config import (
    GEMINI_API_KEY, GEMINI_MODEL, DEFAULT_ENGINE,
    POPPLER_PATH, OUTPUT_DIR, validate_config,
)
from utils.usage_tracker import UsageTracker
from utils.page_spec import parse_page_spec
from utils.io import ParserError, _safe_write_text
from extractors import toc_parser as toc_parser_module


# ────────────────────────────────────────────────────────────
# 헬퍼 함수
# ────────────────────────────────────────────────────────────

def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ps-docparser",
        description="범용 PDF → 마크다운 변환기 (하이브리드: pdfplumber + AI 엔진)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
페이지 지정 예시:
  --pages 15        → 1~15페이지
  --pages 16-30     → 16~30페이지
  --pages 1,3,5-10  → 1, 3, 5~10페이지
  --pages 20-       → 20페이지~끝

엔진:
  gemini     Google Gemini Vision (기본, API 키 필요, 고품질)
  local      pdfplumber 자체 파싱 (무료, Poppler 불필요, 저품질)
  zai        Z.ai GLM-OCR (BOM 도면 전용, API 키 필요)
  mistral    Mistral Pixtral OCR (폴백, API 키 필요)
  tesseract  Tesseract 로컬 OCR (오프라인, 무료)

프리셋:
  pumsem   건설 품셈 전용 (부문명 줄바꿈 보정 활성화)
  estimate 견적서 전용 (Excel 시트 구성 최적화)
  bom      BOM 도면 전용 (OCR 엔진 필수)

배치 처리:
  입력을 디렉토리로 지정하면 하위 PDF 파일 전체를 순차 처리한다.
  예) python main.py ./pdfs/ --preset bom --output excel
        """,
    )
    parser.add_argument(
        "input",
        metavar="파일-또는-디렉토리",
        help="처리할 파일 (.pdf 또는 .md) 또는 PDF 디렉토리",
    )
    parser.add_argument(
        "--engine",
        default=None,
        choices=["gemini", "local", "zai", "mistral", "tesseract"],
        help=f"AI 엔진 선택 (기본: .env의 DEFAULT_ENGINE={DEFAULT_ENGINE})",
    )
    parser.add_argument(
        "--text-only", "-t",
        action="store_true",
        help="텍스트 전용 모드 (AI 미사용, 무료, 빠름)",
    )
    parser.add_argument(
        "--toc",
        default=None,
        metavar="파일",
        help="목차 파일 경로 (.json 또는 .txt)",
    )
    parser.add_argument(
        "--pages",
        default=None,
        metavar="지정",
        help="처리할 페이지 범위 (예: 1-15, 20-, 1,3,5-10)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        metavar="경로",
        help=f"출력 폴더 (기본: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--preset",
        default=None,
        choices=["pumsem", "estimate", "bom"],
        help="도메인 프리셋 (기본: 없음=범용)",
    )
    parser.add_argument(
        "--output",
        default="md",
        choices=["md", "json", "excel"],
        dest="output_format",
        help="출력 형식 (기본: md) - json 시 Phase 2, excel 시 Phase 3 실행",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="설정 오류가 있어도 강제로 실행 (Phase 6)",
    )
    return parser


def _create_engine(engine_name: str, tracker=None):
    """
    엔진명으로 엔진 인스턴스를 생성한다.

    Phase 5: sys.exit() → raise ParserError()
        배치 루프에서 엔진 생성 실패 시 해당 파일만 건너뛰고 계속 진행한다.
    """
    if engine_name == "gemini":
        from engines.gemini_engine import GeminiEngine
        return GeminiEngine(config.GEMINI_API_KEY, config.GEMINI_MODEL, tracker)
    elif engine_name == "local":
        from engines.local_engine import LocalEngine
        return LocalEngine()
    elif engine_name == "zai":
        from engines.zai_engine import ZaiEngine
        if not config.ZAI_API_KEY:
            raise ParserError(".env에 ZAI_API_KEY가 설정되지 않았습니다.")
        return ZaiEngine(config.ZAI_API_KEY, tracker=tracker)
    elif engine_name == "mistral":
        from engines.mistral_engine import MistralEngine
        if not config.MISTRAL_API_KEY:
            raise ParserError(".env에 MISTRAL_API_KEY가 설정되지 않았습니다.")
        return MistralEngine(config.MISTRAL_API_KEY, tracker=tracker)
    elif engine_name == "tesseract":
        from engines.tesseract_engine import TesseractEngine
        return TesseractEngine(tesseract_path=config.TESSERACT_PATH)
    else:
        raise ParserError(f"알 수 없는 엔진: {engine_name}")


def _load_toc(toc_path: str) -> dict | None:
    """
    목차 파일을 로드하여 section_map을 반환한다.

    Phase 5: sys.exit() → raise ParserError()
    """
    if not os.path.exists(toc_path):
        raise ParserError(f"목차 파일을 찾을 수 없습니다: {toc_path}")

    if toc_path.endswith(".json"):
        print(f"목차 JSON 파일 로드 중: {toc_path}")
        with open(toc_path, "r", encoding="utf-8") as f:
            toc_data = json.load(f)
        section_map = toc_data.get("section_map", {})
        print(f"    JSON에서 {len(section_map)}개 섹션 정보 로드 완료")
    else:
        print(f"목차 파일 파싱 중: {toc_path}")
        section_map = toc_parser_module.parse_toc_file(toc_path)
        print(f"    {len(section_map)}개 페이지에 대한 목차 정보 파싱 완료")

    return section_map


def _get_output_path(output_dir: Path, pdf_path: str, page_indices: list | None) -> Path:
    """중복 없는 출력 파일 경로를 생성한다."""
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_stem = Path(pdf_path).stem
    date_str = datetime.now().strftime("%Y%m%d")

    page_range_str = ""
    if page_indices:
        page_range_str = f"_p{min(page_indices)+1}-{max(page_indices)+1}"

    base_name = f"{date_str}_{pdf_stem}{page_range_str}"
    output_path = output_dir / f"{base_name}.md"

    # 중복 파일명 처리
    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{base_name}_{counter}.md"
        counter += 1

    return output_path


class _Tee:
    """stdout을 파일과 콘솔에 동시 출력한다."""
    def __init__(self, *files):
        self.files = files

    def write(self, obj):
        for f in self.files:
            try:
                f.write(obj)
                f.flush()
            except UnicodeEncodeError:
                # Why: Windows CP949 콘솔은 이모지/em-dash 등 BMP 외 문자를 처리 못한다.
                #      크래시 대신 해당 문자를 '?'로 치환하여 배치가 중단되지 않도록 한다.
                # 로그 파일(UTF-8)은 원본 그대로 쓰고, 콘솔만 치환한다.
                enc = getattr(f, 'encoding', 'utf-8') or 'utf-8'
                safe = obj.encode(enc, errors='replace').decode(enc)
                f.write(safe)
                f.flush()

    def flush(self):
        for f in self.files:
            f.flush()


# ────────────────────────────────────────────────────────────
# 단일 파일 파이프라인 (Phase 5: _process_single 분리)
# ────────────────────────────────────────────────────────────

def _process_single(
    args,
    input_path: Path,
    out_dir: Path,
    cache,          # TableCache | None
    tracker: "UsageTracker",
) -> None:
    """
    단일 파일에 대한 전체 파이프라인을 실행한다.

    Why 분리:
        배치 루프에서 이 함수를 try/except로 감싸면
        단일 파일 실패가 전체 배치를 중단시키지 않는다.
        main()은 파일 목록 관리와 캐시 생명주기만 담당한다.

    Args:
        args:        argparse.Namespace (CLI 인수)
        input_path:  처리할 단일 파일 경로 (Path)
        out_dir:     출력 디렉토리 (Path)
        cache:       TableCache 인스턴스 또는 None (CACHE_ENABLED=false 시)
        tracker:     UsageTracker 인스턴스

    Raises:
        ParserError: 복구 불가능한 처리 오류 (배치 루프에서 catch 후 continue)
    """
    input_path = Path(input_path)
    is_md_input = input_path.suffix.lower() == ".md"

    # ── .md 입력 + --output md 조합 경고 ──
    if is_md_input and args.output_format == "md":
        raise ParserError(
            ".md 파일 입력 시 --output json 을 사용하세요. "
            "--output md 는 Phase 1(PDF→MD) 전용입니다."
        )

    # ── --text-only + --output json/excel 안내 ──
    if args.text_only and args.output_format in ("json", "excel"):
        print("  [참고] --text-only와 --output json/excel 병용: "
              "텍스트 전용으로 추출한 뒤 파싱합니다.")

    # ── 프리셋 로딩 ──
    division_names = None
    parse_patterns = None
    type_keywords = None
    excel_config = None
    cover_metadata = None
    preset = args.preset

    if preset == "pumsem":
        from presets.pumsem import (
            get_division_names,
            get_parse_patterns,
            get_table_type_keywords,
        )
        division_names = get_division_names()
        parse_patterns = get_parse_patterns()
        type_keywords = get_table_type_keywords()
        print(f"  프리셋 활성화: {preset} (부문명·파서 패턴·테이블 키워드 로드 완료)")

    elif preset == "estimate":
        from presets.estimate import (
            get_table_type_keywords as _get_est_keywords,
            get_excel_config,
        )
        type_keywords = _get_est_keywords()
        excel_config = get_excel_config()
        print(f"  프리셋 활성화: {preset} (테이블 키워드 + Excel 시트 구성 로드 완료)")

    elif preset == "bom":
        # ── BOM 전용 파이프라인 ──
        from presets.bom import get_bom_keywords, get_image_settings
        bom_keywords = get_bom_keywords()
        image_settings = get_image_settings()
        engine_name = args.engine or config.BOM_DEFAULT_ENGINE
        print(f"  프리셋: bom (엔진: {engine_name})")

        bom_engine = _create_engine(engine_name, tracker)
        if not bom_engine.supports_ocr:
            raise ParserError(
                f"BOM 프리셋은 OCR 엔진(zai/mistral/tesseract)이 필요합니다. "
                f"현재: {engine_name} → --engine zai 로 변경하세요."
            )

        # Phase 5: 캐시 주입
        # Why: bom_engine.cache가 None이 아니면 ocr_document()가 DB 적중 시 API를 건너뛴다.
        if cache is not None:
            bom_engine.cache = cache

        out_dir.mkdir(parents=True, exist_ok=True)
        input_stem = input_path.stem
        date_str = datetime.now().strftime("%Y%m%d")
        output_base = out_dir / f"{date_str}_{input_stem}_bom"

        page_indices = None
        if args.pages:
            import pdfplumber
            with pdfplumber.open(str(input_path)) as pdf:
                total_pages = len(pdf.pages)
            page_indices = parse_page_spec(args.pages, total_pages)

        print(f"\n  {'='*50}")
        print(f"  Phase 1-BOM: OCR 추출 (엔진: {engine_name})")
        print(f"  {'='*50}")

        from extractors.bom_extractor import extract_bom_with_retry, to_sections
        bom_result = extract_bom_with_retry(
            bom_engine, input_path, bom_keywords, image_settings, page_indices
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

        if args.output_format == "excel":
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
        return  # BOM 파이프라인 종료 → 표준 파이프라인 건너뜀

    # ── .md 직접 입력 모드: Phase 1 스킵 ──
    section_map = None
    md = None
    md_source = None

    if is_md_input:
        md_source = str(input_path)
    else:
        # ── 엔진 결정 (PDF 입력 시) ──
        engine_name = args.engine or DEFAULT_ENGINE

        if args.text_only:
            engine = None
            print("  모드: 텍스트 전용 (엔진 없음)")
        elif engine_name in ("gemini",):
            from engines.gemini_engine import GeminiEngine
            engine = GeminiEngine(
                api_key=GEMINI_API_KEY,
                model=GEMINI_MODEL,
                tracker=tracker,
            )
            print(f"  엔진: GeminiEngine (모델: {GEMINI_MODEL})")
        elif engine_name == "local":
            from engines.local_engine import LocalEngine
            engine = LocalEngine()
            print("  엔진: LocalEngine (API 없음, Poppler 불필요)")
        else:
            raise ParserError(f"표준 파이프라인에서 지원하지 않는 엔진: {engine_name}. "
                              f"BOM 전용 엔진은 --preset bom과 함께 사용하세요.")

        # ── 페이지 범위 파싱 ──
        import pdfplumber
        with pdfplumber.open(str(input_path)) as pdf:
            total_pages = len(pdf.pages)

        page_indices = None
        if args.pages:
            page_indices = parse_page_spec(args.pages, total_pages)
            if not page_indices:
                raise ParserError(
                    f"유효한 페이지가 없습니다: {args.pages} (총 {total_pages}페이지)"
                )
            print(f"  페이지 지정: {args.pages} → {len(page_indices)}페이지 처리 예정")

        # ── 목차 로딩 ──
        if args.toc:
            section_map = _load_toc(args.toc)

    # ── Phase 1: PDF → MD (PDF 입력 시) ──
    if not is_md_input:
        out_dir.mkdir(parents=True, exist_ok=True)

        if args.text_only:
            from extractors.text_extractor import process_pdf_text_only
            md = process_pdf_text_only(
                str(input_path),
                section_map=section_map,
                page_indices=page_indices,
                toc_parser_module=toc_parser_module if section_map else None,
                preset=preset,
                division_names=division_names,
            )
        else:
            from extractors.hybrid_extractor import process_pdf
            md = process_pdf(
                str(input_path),
                engine=engine,
                section_map=section_map,
                page_indices=page_indices,
                toc_parser_module=toc_parser_module if section_map else None,
                preset=preset,
                division_names=division_names,
            )

        if not md:
            raise ParserError("추출 결과가 없습니다.")

        # MD 저장
        page_indices_local = page_indices if args.pages else None
        md_path = _get_output_path(out_dir, str(input_path), page_indices_local)
        _safe_write_text(md_path, md)

        print(f"  MD 출력: {md_path.name} ({len(md):,} bytes)")

        if args.output_format == "md":
            print()
            print("  완료!")
            if tracker.call_count > 0:
                print(tracker.summary())
            return

        md_source = str(md_path)

    # ── Phase 2: MD → JSON ──
    print()
    print("  ── Phase 2: 마크다운 → JSON 파싱 시작 ──")
    from parsers.document_parser import parse_markdown

    toc_path_for_parser = args.toc if args.toc and args.toc.endswith(".json") else None

    if md is not None:
        # PDF에서 추출한 MD 텍스트를 직접 파서에 전달
        sections = parse_markdown(
            md,
            toc_path=toc_path_for_parser,
            type_keywords=type_keywords,
            patterns=parse_patterns,
        )
    else:
        # .md 파일 직접 입력
        sections = parse_markdown(
            md_source,
            toc_path=toc_path_for_parser,
            type_keywords=type_keywords,
            patterns=parse_patterns,
        )

    print(f"  파싱 완료: {len(sections)}개 섹션")

    # JSON 저장
    input_stem = input_path.stem
    date_str = datetime.now().strftime("%Y%m%d")
    json_name = f"{date_str}_{input_stem}.json"
    json_path = out_dir / json_name
    counter = 1
    while json_path.exists():
        json_path = out_dir / f"{date_str}_{input_stem}_{counter}.json"
        counter += 1

    from exporters.json_exporter import JsonExporter
    JsonExporter().export(sections, json_path)

    print(f"  JSON 저장: {json_path.name}")
    tables_total = sum(len(s.get("tables", [])) for s in sections)
    print(f"  섹션 수: {len(sections)}  /  테이블 수: {tables_total}")

    # Phase 1 완료 후 프리셋 미지정 시 문서 유형 제안
    if preset is None and md:
        from detector import suggest_preset
        suggestion = suggest_preset(md)
        if suggestion:
            print(suggestion)

    # ── Phase 3: JSON → Excel ──
    if args.output_format == "excel":
        print()
        print("  ── Phase 3: JSON → Excel 변환 시작 ──")
        from exporters.excel_exporter import ExcelExporter

        xlsx_name = f"{date_str}_{input_path.stem}.xlsx"
        xlsx_path = out_dir / xlsx_name
        xlsx_counter = 1
        while xlsx_path.exists():
            xlsx_path = out_dir / f"{date_str}_{input_path.stem}_{xlsx_counter}.xlsx"
            xlsx_counter += 1

        exporter = ExcelExporter()

        if preset == "estimate" and sections:
            from presets.estimate import extract_cover_metadata
            cover_metadata = extract_cover_metadata(
                sections[0].get("clean_text", "")
            )
            print(f"     표지 메타 추출: {cover_metadata.get('serial_no', '(없음)')}")

        exporter.export(
            sections, xlsx_path,
            metadata=cover_metadata,
            preset_config=excel_config,
        )
        print(f"  Excel 출력: {xlsx_path.name}")

    print()
    print("  완료!")
    if tracker.call_count > 0:
        print(tracker.summary())


# ────────────────────────────────────────────────────────────
# 진입점
# ────────────────────────────────────────────────────────────

def main():
    parser = _build_argument_parser()
    args = parser.parse_args()

    # ── 설정 검증 (Phase 6) ──
    validation = validate_config(verbose=True)
    if validation["errors"] and not args.force:
        print("설정 오류로 중단합니다. --force 옵션으로 강제 실행 가능.")
        sys.exit(1)

    input_path = Path(args.input)

    # ── 입력 경로 존재 확인 ──
    if not input_path.exists():
        print(f"오류: 경로를 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    # ── 출력 경로 결정 ──
    out_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR

    # ── Phase 5: 캐시 초기화 ──
    cache = None
    if config.CACHE_ENABLED:
        from cache.table_cache import TableCache
        db_path = config.CACHE_DIR / "table_cache.db"
        cache = TableCache(db_path, ttl_days=config.CACHE_TTL_DAYS)
        # 시작 시 만료 엔트리 정리
        cache.clear_expired()
        print(f"[캐시] 활성화 (DB: {db_path.name}, TTL: {config.CACHE_TTL_DAYS}일)")
    else:
        print("[캐시] 비활성화 (CACHE_ENABLED=false)")

    # ── 로그 파일 설정 ──
    log_file = _project_root / "ps-docparser.log"

    # ── 파일 목록 수집 (단일 파일 또는 배치 디렉토리) ──
    if input_path.is_dir():
        # Phase 5: 배치 처리 — 하위 PDF 전체를 알파벳순으로 정렬하여 처리
        pdf_files = sorted(input_path.glob("*.pdf"))
        if not pdf_files:
            print(f"오류: 디렉토리에 PDF 파일이 없습니다: {input_path}")
            sys.exit(1)
        print(f"\n[배치 모드] {len(pdf_files)}개 PDF 파일 발견 -- {input_path}")
        is_batch = True
    else:
        pdf_files = [input_path]
        is_batch = False

    # ── 실행 ──
    succeeded = []
    failed = []

    with open(log_file, "w", encoding="utf-8") as log:
        original_stdout = sys.stdout
        sys.stdout = _Tee(sys.stdout, log)

        try:
            if is_batch:
                print(f"\n{'='*55}")
                print(f"ps-docparser 배치 시작 ({len(pdf_files)}건)")
                print(f"{'='*55}")
                print(f"  출력 폴더: {out_dir}")
                print(f"  플랫폼: {platform.system()}")
                if args.preset:
                    print(f"  프리셋: {args.preset}")
                print()

                for idx, pdf_path in enumerate(pdf_files, start=1):
                    print(f"[{idx:02d}/{len(pdf_files):02d}] {pdf_path.name}")
                    tracker = UsageTracker()
                    try:
                        _process_single(args, pdf_path, out_dir, cache, tracker)
                        succeeded.append(pdf_path.name)
                        print(f"  → 성공\n")
                    except ParserError as e:
                        import logging
                        failed.append((pdf_path.name, str(e)))
                        logging.getLogger(__name__).error(f"❌ {pdf_path.name}: {e}")
                        print(f"  → 건너뜀: {e}\n")
                        continue
                    except KeyboardInterrupt:
                        print("\n사용자 중단.")
                        break
                    except Exception as e:
                        import logging, traceback
                        failed.append((pdf_path.name, f"예상 못한 오류: {type(e).__name__}: {e}"))
                        logging.getLogger(__name__).exception(f"❌ {pdf_path.name}: 예상 못한 오류")
                        print(f"  → 오류: {e}")
                        traceback.print_exc()
                        print()
                        continue

                # ── 배치 최종 요약 ──
                print("=" * 55)
                print(f"배치 완료: 성공 {len(succeeded)}건 / 실패 {len(failed)}건 / 전체 {len(pdf_files)}건")
                if failed:
                    print("\n[실패 목록]")
                    for fname, reason in failed:
                        print(f"  - {fname}: {reason}")
                print("=" * 55)

                # ── Phase 5 단위 4: 배치 BOM 집계 xlsx 자동 생성 ──
                # Why: --preset bom + --output excel 조합에서 배치가 완료되면
                #      개별 JSON들을 한 시트로 병합한 집계 파일을 자동으로 생성한다.
                #      사용자가 별도 명령을 실행하지 않아도 된다는 것이 핵심 편의점.
                if args.preset == "bom" and args.output_format == "excel" and succeeded:
                    print()
                    print("── BOM 배치 집계 ──")
                    try:
                        from exporters.bom_aggregator import export_aggregated_excel
                        from datetime import datetime as _dt

                        # 성공한 PDF 파일명 → 같은 output_dir 안의 JSON 경로 역추적
                        date_str = _dt.now().strftime("%Y%m%d")
                        json_files: list[Path] = []
                        for pdf_name in succeeded:
                            stem = Path(pdf_name).stem
                            # _process_single이 저장한 JSON 파일명 패턴: {date}_{stem}_bom.json
                            candidates = list(out_dir.glob(f"*_{stem}_bom.json"))
                            if candidates:
                                json_files.append(sorted(candidates)[-1])  # 가장 최신

                        if json_files:
                            agg_path = out_dir / f"{date_str}_BOM집계.xlsx"
                            # 중복 파일명 방지
                            _c = 1
                            while agg_path.exists():
                                agg_path = out_dir / f"{date_str}_BOM집계_{_c}.xlsx"
                                _c += 1

                            result = export_aggregated_excel(json_files, agg_path)
                            print(f"  집계 파일 생성 완료: {result.name}")
                            print(f"  대상 JSON: {len(json_files)}개 → {agg_path.name}")
                        else:
                            print("  ⚠️ 집계할 JSON 파일을 찾지 못했습니다. (출력 폴더 확인 필요)")
                    except Exception as _agg_err:
                        import traceback as _tb
                        print(f"  ⚠️ BOM 집계 중 오류 (배치 결과는 보존됨): {_agg_err}")
                        _tb.print_exc()
                    print("=" * 55)

            else:
                # 단일 파일 처리
                print("=" * 55)
                print("ps-docparser 시작")
                print("=" * 55)
                print(f"  입력: {input_path}")
                print(f"  출력 형식: {args.output_format}")
                print(f"  플랫폼: {platform.system()}")
                if not input_path.suffix.lower() == ".md":
                    print(f"  Poppler: {POPPLER_PATH or '시스템 PATH 사용'}")
                if args.preset:
                    print(f"  프리셋: {args.preset}")
                print()

                tracker = UsageTracker()
                try:
                    _process_single(args, input_path, out_dir, cache, tracker)
                    print()
                    print("=" * 55)
                    print("완료!")
                    print("=" * 55)
                except ParserError as e:
                    print(f"\n오류: {e}")
                    sys.exit(1)
                except KeyboardInterrupt:
                    print("\n사용자에 의해 중단됨")
                except Exception as e:
                    import logging, traceback
                    logging.getLogger(__name__).error(f"오류 발생: {e}")
                    traceback.print_exc()

        except KeyboardInterrupt:
            print("\n\n사용자에 의해 배치가 중단되었습니다.")
            if succeeded:
                print(f"  처리 완료: {len(succeeded)}건 — {', '.join(succeeded)}")
        finally:
            sys.stdout = original_stdout

    # ── Phase 5: 캐시 통계 출력 ──
    if cache is not None:
        stats = cache.stats()
        print(
            f"[캐시 통계] 적중 {stats['hits']}회 / 미스 {stats['misses']}회 "
            f"/ 적중률 {stats['hit_rate_pct']}% / 저장 {stats['size']}건"
        )
        cache.close()


if __name__ == "__main__":
    main()
