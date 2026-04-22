"""
parsers/section_toc.py — 목차(TOC) 로딩 및 역매핑 유틸리티

Why: Phase 12 Step 12-5 분해 결과물.
     section_splitter.py의 TOC 관련 로직(load_toc, build_reverse_map)을
     분리한 순수 TOC 모듈.
     외부 의존성: json, pathlib만 사용.

원본: parsers/section_splitter.py L52~92
"""

import json
from pathlib import Path


def load_toc(toc_path: Path) -> dict:
    """
    목차 JSON 파일을 로드하여 section_map 딕셔너리를 반환한다.

    Args:
        toc_path: 목차 JSON 파일 Path 객체

    Returns:
        dict: section_map {"section_id": {"id":..., "title":..., ...}, ...}
              파일 없으면 빈 dict

    원본: section_splitter.py L52~69
    """
    if not toc_path.exists():
        return {}
    with open(toc_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("section_map", data)


def build_reverse_map(toc: dict) -> dict:
    """
    (section_id, department) → toc_key 역매핑을 생성한다.

    Why: 마커에서 추출한 section_id + department 조합으로
         원본 toc_key를 역방향으로 찾기 위해 사용.

    Args:
        toc: load_toc()가 반환한 section_map

    Returns:
        dict: {(base_id, department): toc_key, ...}

    원본: section_splitter.py L72~92
    """
    reverse = {}
    for toc_key, entry in toc.items():
        base_id = entry.get("id", toc_key.split("#")[0])
        department = entry.get("chapter", "")
        reverse[(base_id, department)] = toc_key
    return reverse
