"""
exporters/json_exporter.py — JSON 파일 저장 Exporter

Why: 현재 main.py에 인라인된 json.dump() 호출을
     BaseExporter 인터페이스에 맞춰 독립 모듈로 분리한다.
     인코딩/indent 등 저장 설정을 한 곳에서 관리할 수 있다.
"""
import json
from pathlib import Path

from exporters.base_exporter import BaseExporter


class JsonExporter(BaseExporter):
    """JSON 섹션 리스트를 파일로 저장한다."""

    file_extension = ".json"

    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        JSON 파일로 저장한다.

        metadata가 있으면 최상위에 문서 메타데이터를 병합:
            {"metadata": {...}, "sections": [...]}
        metadata가 없으면 기존 동작 유지 (섹션 배열만 저장):
            [...]

        Why: metadata=None 케이스에서 기존 json.dump() 출력과
             바이트 단위로 동일한 결과를 생성한다.
             (utf-8-sig, indent=2, ensure_ascii=False 동일)
        """
        if metadata:
            output_data = {"metadata": metadata, "sections": sections}
        else:
            output_data = sections

        from utils.io import _safe_write_text

        json_str = json.dumps(output_data, ensure_ascii=False, indent=2)
        _safe_write_text(output_path, json_str, encoding="utf-8-sig")

        return Path(output_path)
