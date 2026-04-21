"""
scripts/manual_ocr_smoke.py — Phase 4 OCR 파이프라인 수동 스모크 테스트

실행: python scripts/manual_ocr_smoke.py [PDF_PATH]
목적:
    실제 PDF 한 장을 ZAI/Gemini 엔진으로 처리하여
    OCR → BOM 추출 → 섹션 반환 전 과정을 수동 검증한다.
    API 비용이 발생하므로 자동화 CI에서는 실행하지 않는다.

사용 예:
    python scripts/manual_ocr_smoke.py path/to/sample.pdf
    python scripts/manual_ocr_smoke.py path/to/sample.pdf --engine gemini
"""

import sys
import json
import argparse
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def run_smoke(pdf_path: Path, engine_name: str = "zai") -> None:
    import config
    from engines.factory import create_engine
    from utils.usage_tracker import UsageTracker
    from extractors.bom_extractor import extract_bom_with_retry, to_sections
    from presets.bom import get_bom_keywords

    print(f"\n{'='*60}")
    print(f"  OCR Smoke Test")
    print(f"  PDF   : {pdf_path.name}")
    print(f"  Engine: {engine_name}")
    print(f"{'='*60}\n")

    if not pdf_path.exists():
        print(f"[ERROR] PDF 파일 없음: {pdf_path}")
        sys.exit(1)

    tracker = UsageTracker()
    args_ns = argparse.Namespace(
        engine=engine_name,
        gemini_key=config.GEMINI_API_KEY,
        zai_key=config.ZAI_API_KEY,
        mistral_key=config.MISTRAL_API_KEY,
        tesseract_path=config.TESSERACT_PATH,
    )

    try:
        engine = create_engine(args_ns, tracker)
    except Exception as e:
        print(f"[ERROR] 엔진 생성 실패: {e}")
        sys.exit(1)

    print(f"[1/3] 엔진 생성 완료: {type(engine).__name__}")

    try:
        pages = engine.ocr_document(pdf_path)
        full_text = "\n".join(p.text for p in pages)
        print(f"[2/3] OCR 완료: {len(pages)} 페이지, {len(full_text)} 문자")
    except Exception as e:
        print(f"[ERROR] OCR 실패: {e}")
        sys.exit(1)

    try:
        kw = get_bom_keywords()
        result = extract_bom_with_retry(full_text, kw)
        sections = to_sections(result)
        print(f"[3/3] BOM 추출: {len(sections)} 섹션, {result.total_bom_rows} 행")
        print()
        print(json.dumps(sections, ensure_ascii=False, indent=2)[:2000])
        print("\n✅ 스모크 테스트 완료")
    except Exception as e:
        print(f"[ERROR] BOM 추출 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCR 파이프라인 수동 스모크 테스트")
    parser.add_argument("pdf", type=Path, help="테스트할 PDF 파일 경로")
    parser.add_argument("--engine", default="zai", choices=["zai", "gemini", "mistral", "tesseract", "local"])
    args = parser.parse_args()
    run_smoke(args.pdf, args.engine)
