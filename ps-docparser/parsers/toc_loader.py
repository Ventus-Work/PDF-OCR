"""목차 파일 로딩. (main.py _load_toc 추출)"""

import json
import os

from extractors import toc_parser as toc_parser_module
from utils.io import ParserError


def load_toc(toc_path: str) -> dict:
    """목차 파일을 로드하여 section_map을 반환한다."""
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
