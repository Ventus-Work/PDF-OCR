from extractors.extraction_quality import evaluate_document_extraction


def test_evaluate_document_extraction_marks_tiny_scan_as_weak():
    metrics = evaluate_document_extraction("<!-- PAGE 1 -->\n\n스캔", expected_pages=1)

    assert metrics.too_weak is True
    assert "visible_chars<200" in metrics.weak_reason


def test_evaluate_document_extraction_marks_material_quote_without_tables_as_weak():
    md_text = (
        "<!-- PAGE 1 -->\n\n"
        "견적서\n거래처 PS산업\n품목 아연도금강판 재질 GI 치수 1000x2000 "
        "수량 3 중량 120 단가 1000 단위 KG 공급가액 120000 메모 없음"
    )

    metrics = evaluate_document_extraction(md_text, expected_pages=1)

    assert metrics.material_quote_detected is True
    assert metrics.too_weak is True
    assert "material_quote_without_table_signal" in metrics.weak_reason


def test_evaluate_document_extraction_accepts_structured_html_table():
    md_text = (
        "<!-- PAGE 1 -->\n\n"
        "<table><tr><th>No</th><th>품목</th></tr>"
        "<tr><td>1</td><td>아연도금강판</td></tr></table>\n\n"
        + ("상세내용" * 90)
    )

    metrics = evaluate_document_extraction(md_text, expected_pages=1)

    assert metrics.html_table_count == 1
    assert metrics.too_weak is False
