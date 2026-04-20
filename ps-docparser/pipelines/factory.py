"""프리셋 → 파이프라인 팩토리. (spec §4.5)"""

from pipelines.base import PipelineContext
from pipelines.bom_pipeline import BomPipeline
from pipelines.document_pipeline import DocumentPipeline


def create_pipeline(context: PipelineContext):
    """프리셋에 따라 적절한 파이프라인 인스턴스를 반환한다."""
    preset = getattr(context.args, "preset", None)
    if preset == "bom":
        return BomPipeline(context)
    return DocumentPipeline(context)
