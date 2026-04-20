"""
utils/ocr_utils.py — OCR 엔진 공통 유틸리티

Why: ZaiEngine, MistralEngine, bom_extractor에서 중복되는
     base64 변환 및 PDF→이미지 변환 로직을 1곳으로 통합한다.

Dependencies: Pillow, pdf2image, config.POPPLER_PATH
"""
import base64
import io
from pathlib import Path

from PIL import Image


def file_to_data_uri(file_path: Path) -> str:
    """파일을 base64 data URI로 변환한다."""
    file_path = Path(file_path)
    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
    ext = file_path.suffix.lower().lstrip(".")
    if ext == "pdf":
        mime = "application/pdf"
    elif ext in ("png", "jpg", "jpeg"):
        mime = f"image/{ext}"
    else:
        mime = "application/octet-stream"
    return f"data:{mime};base64,{content}"


def image_to_data_uri(image: Image.Image) -> str:
    """PIL 이미지를 base64 PNG data URI로 변환한다."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    content = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{content}"


def pdf_page_to_image(
    file_path: Path, page_idx: int, dpi: int = 400
) -> Image.Image:
    """
    PDF 특정 페이지를 PIL 이미지로 변환한다.

    Args:
        file_path: PDF 파일 경로
        page_idx: 페이지 인덱스 (0-based)
        dpi: 해상도 (기본 400)

    Returns:
        PIL Image
    """
    from pdf2image import convert_from_path
    from config import POPPLER_PATH

    images = convert_from_path(
        str(file_path),
        first_page=page_idx + 1,
        last_page=page_idx + 1,
        dpi=dpi,
        poppler_path=POPPLER_PATH,
    )
    return images[0]
