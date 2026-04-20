"""
exporters/base_exporter.py — 내보내기 공통 인터페이스 (Abstract Base Class)

Why: engines/base_engine.py와 동일한 Strategy Pattern.
     새 출력 형식 추가 시 이 클래스를 상속하면 main.py가 자동 인식.
     ExcelExporter, JsonExporter 등이 공통 시그니처를 준수하도록 강제.
"""
from abc import ABC, abstractmethod
from pathlib import Path


class BaseExporter(ABC):
    """출력 파일 생성기의 공통 인터페이스."""

    @abstractmethod
    def export(
        self,
        sections: list[dict],
        output_path: Path,
        *,
        metadata: dict | None = None,
        preset_config: dict | None = None,
    ) -> Path:
        """
        JSON 섹션 리스트를 출력 파일로 변환한다.

        Args:
            sections: Phase 2 출력 JSON 배열
            output_path: 출력 파일 경로
            metadata: 문서 메타데이터 (표지 정보 등)
            preset_config: 프리셋별 출력 설정 (시트 구성, 열 매핑 등)

        Returns:
            실제로 저장된 파일 경로
        """
        ...

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """이 Exporter가 생성하는 파일 확장자 (예: '.xlsx')."""
        ...
