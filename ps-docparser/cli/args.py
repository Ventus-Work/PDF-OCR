"""CLI 인수 파서. (--no-cache, --no-bom-fallback 포함)"""

import argparse

import config


def build_argument_parser() -> argparse.ArgumentParser:
    """CLI 인수 파서를 빌드하여 반환한다."""
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
  generic  범용 문서 경로 강제 (자동 라우팅 건너뜀)
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
        help=f"AI 엔진 선택 (기본: .env의 DEFAULT_ENGINE={config.DEFAULT_ENGINE})",
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
        help=f"출력 폴더 (기본: {config.OUTPUT_DIR})",
    )
    parser.add_argument(
        "--preset",
        default=None,
        choices=["generic", "pumsem", "estimate", "bom"],
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
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="테이블 캐시 비활성화 (재실행 강제 시 유용)",
    )
    parser.add_argument(
        "--no-bom-fallback",
        action="store_true",
        help="BOM 자동 estimate 재실행 비활성화 (--bom-fallback never 호환 별칭)",
    )
    parser.add_argument(
        "--bom-fallback",
        default="auto",
        choices=["auto", "always", "never"],
        help="BOM estimate 보조 산출물 생성 정책 (기본: auto)",
    )
    return parser
