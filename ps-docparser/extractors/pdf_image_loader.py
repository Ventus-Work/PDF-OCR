"""
extractors/pdf_image_loader.py — PDF 페이지 이미지 레이지 로더

Why: hybrid_extractor.py에서 pdf2image.convert_from_path를 페이지 루프마다
     호출하면 같은 PDF를 N회 재변환하여 메모리 수 GB를 소모했다.
     이 모듈은 페이지 단위로 필요할 때만 변환하고, LRU 캐시로
     동일 페이지의 재변환을 방지한다.

사용:
    loader = PdfImageLoader(pdf_path, poppler_path=POPPLER_PATH)
    img = loader.get_page(3)   # 1-indexed
    ...
    loader.close()             # 루프 종료 후 메모리 즉시 해제

Phase 8: §2.2 설계 기반
"""
import logging
from functools import lru_cache

from pdf2image import convert_from_path

logger = logging.getLogger(__name__)


class PdfImageLoader:
    """
    PDF의 개별 페이지를 필요 시점에 이미지로 변환 (Lazy + LRU 캐시).

    Args:
        pdf_path:     PDF 파일 경로
        poppler_path: Poppler 바이너리 경로 (None이면 시스템 PATH 사용)
        dpi:          이미지 해상도 (기본 200)
        cache_size:   LRU 캐시 크기 — 기본 4 (페이지 4개 = 약 100MB 이내)

    설계 원칙:
        - first_page=N, last_page=N 으로 단일 페이지만 변환 → 전체 로딩 회피
        - lru_cache(maxsize=cache_size): 최근 N페이지 캐싱, 오래된 것 자동 해제
        - close(): 캐시 전체 clear → PIL Image GC 가능 상태로 전환
        - try/finally 패턴 강제: hybrid_extractor.py에서 항상 close() 보장
    """

    def __init__(
        self,
        pdf_path: str,
        poppler_path: str = None,
        dpi: int = 200,
        cache_size: int = 4,
    ):
        self.pdf_path = pdf_path
        self.poppler_path = poppler_path
        self.dpi = dpi
        # lru_cache를 인스턴스 메서드에 동적 적용
        # Why: 클래스 레벨 캐시는 인스턴스 간 공유되어 메모리 누수 위험.
        #      인스턴스별 캐시로 격리함.
        self._cache = lru_cache(maxsize=cache_size)(self._load_page)

    def _load_page(self, page_num: int):
        """
        페이지 1개만 이미지로 변환 (1-indexed).

        Why: first_page=last_page=N 파라미터로 단일 페이지만 decode.
             전체 PDF를 메모리에 올리지 않아 메모리 소모 최소화.
        """
        logger.debug(f"PDF 이미지 변환: {self.pdf_path} p.{page_num}")
        kwargs = {
            "pdf_path": self.pdf_path,
            "dpi": self.dpi,
            "first_page": page_num,
            "last_page": page_num,
        }
        if self.poppler_path:
            kwargs["poppler_path"] = self.poppler_path

        images = convert_from_path(**kwargs)
        return images[0] if images else None

    def get_page(self, page_num: int):
        """
        페이지 이미지를 반환한다 (1-indexed).

        캐시 히트 시 재변환 없음. 미스 시 _load_page 호출.
        """
        return self._cache(page_num)

    def close(self):
        """
        LRU 캐시를 비워 PIL Image 객체를 GC 대상으로 만든다.

        Why: Python의 lru_cache는 캐시된 객체에 강한 참조를 유지한다.
             cache_clear() 없이는 PIL Image가 메모리에 계속 남아
             대용량 PDF 배치 처리 시 메모리 누수로 이어진다.
        """
        self._cache.cache_clear()
        logger.debug(f"PdfImageLoader 캐시 해제: {self.pdf_path}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
