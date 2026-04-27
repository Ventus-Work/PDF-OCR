"""Quality checks for parsed output tables."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_NUMERIC_RE = re.compile(r"^-?[\d,.]+$")
_DUPLICATE_SUFFIX_RE = re.compile(r"_\d+$")
_EMPTY_TAIL_HEADER_RE = re.compile(r"^(?:Column_|col_)\d+$", re.IGNORECASE)
_UNIT_VALUE_RE = re.compile(
    r"^(?:EA|SET|LOT|M|M2|M3|KG|TON|식|개|대|본|매|조|개소)$",
    re.IGNORECASE,
)
_ESTIMATE_CONDITION_LABELS = {
    "납기": "납기",
    "남기": "납기",
    "운송조건": "운송조건",
    "운습조건": "운송조건",
    "결제조건": "결제조건",
    "착지": "착지",
    "인도조건": "인도조건",
}


def _normalize_header(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("\n", " ")).strip()
    text = _DUPLICATE_SUFFIX_RE.sub("", text)
    return re.sub(r"[\s._|/\-']+", "", text.upper())


def _header_parts(header: Any) -> list[str]:
    return [part.strip() for part in str(header or "").split("|") if part.strip()]


def _is_self_repeating_composite_header(header: Any) -> bool:
    parts = _header_parts(header)
    if len(parts) < 2:
        return False
    return _normalize_header(parts[0]) == _normalize_header(parts[1])


def _is_quantity_header(header: Any) -> bool:
    key = _normalize_header(header)
    return key in {"QTY", "QUANTITY", "수량"} or "수량" in str(header)


def _is_general_unit_header(header: Any) -> bool:
    text = str(header or "")
    keys = {_normalize_header(part) for part in _header_parts(text)}
    key = _normalize_header(text)
    has_unit = key in {"UNIT", "단위"} or bool(keys.intersection({"UNIT", "단위"}))
    if not has_unit:
        return False
    return not any(
        token in text.upper()
        for token in ("WEIGHT", "LOSS", "KG", "M2", "중량", "면적", "자재중량", "자재면적")
    )


def _is_unit_like_header(header: Any) -> bool:
    keys = {_normalize_header(part) for part in _header_parts(header)}
    key = _normalize_header(header)
    return key in {"UNIT", "단위"} or bool(keys.intersection({"UNIT", "단위"}))


def _is_numeric(value: Any) -> bool:
    return bool(_NUMERIC_RE.match(str(value or "").strip()))


def _is_unit_value(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text and _UNIT_VALUE_RE.match(text))


def _row_values(row: Any, headers: list[str]) -> list[Any]:
    if isinstance(row, dict):
        return [row.get(header, "") for header in headers]
    if isinstance(row, (list, tuple)):
        return list(row)
    return [row]


def _header_compact(headers: list[str]) -> str:
    return "".join(_normalize_header(header) for header in headers)


def _table_text(table: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.extend(str(header) for header in table.get("headers", []) or [])
    parts.append(str(table.get("type", "")))
    parts.append(str(table.get("title", "")))
    for row in table.get("rows", [])[:3] or []:
        if isinstance(row, dict):
            parts.extend(str(value) for value in row.values())
        elif isinstance(row, (list, tuple)):
            parts.extend(str(value) for value in row)
        else:
            parts.append(str(row))
    return " ".join(parts)


def _is_material_quantity_table(headers: list[str]) -> bool:
    compact = _header_compact(headers)
    required_hits = sum(
        1
        for keyword in (
            "설치구분",
            "제품",
            "철판종류",
            "치수",
            "재질",
            "개별제품중량",
            "전체중량",
            "전체단면적",
            "도장면적",
        )
        if keyword in compact
    )
    return required_hits >= 5 and "수량" in compact


def _is_bom_material_table(headers: list[str]) -> bool:
    compact = _header_compact(headers)
    bom_hits = sum(
        1
        for keyword in (
            "DESCRIPTION",
            "DWGNO",
            "MATL",
            "SIZE",
            "수량",
            "단위",
            "자재중량",
            "자재면적",
        )
        if keyword in compact
    )
    return bom_hits >= 4 and "DESCRIPTION" in compact


def _is_estimate_item_table(headers: list[str]) -> bool:
    compact = _header_compact(headers)
    hits = sum(
        1
        for keyword in (
            "NO",
            "품목",
            "항목",
            "재질",
            "치수",
            "수량",
            "중량",
            "단가",
            "단위",
            "공급가액",
            "금액",
            "메모",
        )
        if keyword in compact
    )
    return hits >= 5 and any(keyword in compact for keyword in ("품목", "항목"))


def _looks_like_source_info_table(table: dict[str, Any]) -> bool:
    text = _table_text(table)
    hits = sum(
        1
        for keyword in ("상호", "등록번호", "주소", "업태", "전화번호", "입금계좌", "FAX", "사업자등록번호")
        if keyword in text
    )
    return hits >= 3


def _split_header_pair(header: str, value: str) -> list[dict[str, str]]:
    header_parts = [part for part in str(header or "").split("_") if part]
    value_parts = [part for part in str(value or "").split("_") if part]
    if len(header_parts) >= 2 and len(value_parts) >= 2:
        return [
            {"항목": header_parts[0], "값": value_parts[0], "보조항목": "", "보조값": ""},
            {"항목": header_parts[1], "값": value_parts[1], "보조항목": "", "보조값": ""},
        ]
    return []


def _normalize_source_info_table(table: dict[str, Any]) -> dict[str, Any]:
    headers = [str(header) for header in table.get("headers", []) or []]
    rows = table.get("rows", []) or []
    normalized_rows: list[dict[str, str]] = []

    if len(headers) >= 2:
        normalized_rows.extend(_split_header_pair(headers[0], headers[1]))
    if len(headers) >= 4 and "성명" in headers[2]:
        name_value = str(headers[3]).split("_")[-1].strip()
        if name_value:
            normalized_rows.append({"항목": "성명", "값": name_value, "보조항목": "", "보조값": ""})

    for row in rows:
        if not isinstance(row, dict):
            continue
        values = [str(row.get(header, "") or "").strip() for header in headers]
        values.extend([""] * max(0, 4 - len(values)))
        label, value, sub_label, sub_value = values[:4]
        if label and value and value == sub_label == sub_value:
            sub_label = ""
            sub_value = ""
        normalized_rows.append(
            {
                "항목": label,
                "값": value,
                "보조항목": sub_label,
                "보조값": sub_value,
            }
        )

    table["headers"] = ["항목", "값", "보조항목", "보조값"]
    table["rows"] = [
        row
        for row in normalized_rows
        if any(str(value or "").strip() for value in row.values())
    ]
    table["domain"] = "generic"
    table["role"] = "source_info_table"
    table["type"] = "source_info"
    return table


def _common_quality(headers: list[str], rows: list[Any]) -> dict[str, Any]:
    warnings: list[str] = []
    for row in rows:
        if isinstance(row, dict) and list(row.keys()) != headers:
            warnings.append("header_row_key_mismatch")
            break
    unique_warnings = list(dict.fromkeys(warnings))
    status = "fail" if "header_row_key_mismatch" in unique_warnings else "ok"
    return {"status": status, "warnings": unique_warnings}


def _is_empty_value(value: Any) -> bool:
    return not str(value or "").strip()


def _is_empty_tail_header(header: Any) -> bool:
    return bool(_EMPTY_TAIL_HEADER_RE.match(str(header or "").strip()))


def _row_has_empty_tail_value(row: Any, key: str, index: int) -> bool:
    if isinstance(row, dict):
        return _is_empty_value(row.get(key, ""))
    if isinstance(row, (list, tuple)):
        return len(row) <= index or _is_empty_value(row[index])
    return True


def prune_empty_tail_columns(table: dict[str, Any]) -> dict[str, Any]:
    """Remove trailing generated columns that have no values in any row."""

    headers = list(table.get("headers", []) or [])
    rows = table.get("rows", []) or []
    changed = False

    while headers and _is_empty_tail_header(headers[-1]):
        key = headers[-1]
        if not rows:
            break

        index = len(headers) - 1
        if all(_row_has_empty_tail_value(row, key, index) for row in rows):
            headers.pop()
            for row in rows:
                if isinstance(row, dict):
                    row.pop(key, None)
                elif isinstance(row, list) and len(row) > len(headers):
                    row.pop()
            changed = True
            continue
        break

    if changed:
        table["headers"] = headers
    return table


def _row_string_values(row: Any) -> list[str]:
    if isinstance(row, dict):
        values = row.values()
    elif isinstance(row, (list, tuple)):
        values = row
    else:
        values = [row]
    return [str(value or "").strip() for value in values if str(value or "").strip()]


def _normalized_condition_label(value: Any) -> str | None:
    key = re.sub(r"\s+", "", str(value or "").strip())
    return _ESTIMATE_CONDITION_LABELS.get(key)


def _condition_label_from_row(row: Any, headers: list[str]) -> str | None:
    if not isinstance(row, dict):
        return None

    candidates: list[Any] = []
    if headers:
        candidates.append(row.get(headers[0], ""))
    for key in ("No", "NO", "조건", "항목", "품목"):
        if key in row:
            candidates.append(row.get(key, ""))

    for value in candidates:
        label = _normalized_condition_label(value)
        if label:
            return label
    return None


def _looks_like_condition_aggregate_row(row: Any) -> bool:
    values = _row_string_values(row)
    if not values:
        return False
    combined = " ".join(values)
    label_hits = sum(1 for label in _ESTIMATE_CONDITION_LABELS if label in combined)
    has_long_value = any(len(value) >= 50 for value in values)
    return label_hits >= 3 and has_long_value


def _make_condition_row_from_estimate_row(row: dict[str, Any], label: str) -> dict[str, str]:
    values = []
    seen = set()
    for value in _row_string_values(row):
        normalized = re.sub(r"\s+", "", value)
        if _ESTIMATE_CONDITION_LABELS.get(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(value)

    short_values = [value for value in values if len(value) < 45]
    long_values = [value for value in values if len(value) >= 45]
    condition_value = short_values[0] if short_values else ""
    note = long_values[0] if long_values else ""
    return {"조건": label, "값": condition_value, "비고": note}


def _split_estimate_condition_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    headers = [str(header) for header in table.get("headers", []) or []]
    rows = list(table.get("rows", []) or [])
    if not rows or not _is_estimate_item_table(headers):
        return [table]

    kept_rows: list[Any] = []
    condition_rows: list[dict[str, str]] = []
    seen_condition_notes: set[str] = set()
    changed = False

    for row in rows:
        values = _row_string_values(row)
        if any("-이하 여백-" in value for value in values):
            changed = True
            continue

        label = _condition_label_from_row(row, headers)
        if label and isinstance(row, dict):
            condition_row = _make_condition_row_from_estimate_row(row, label)
            note = condition_row.get("비고", "")
            if note:
                if note in seen_condition_notes:
                    condition_row["비고"] = ""
                else:
                    seen_condition_notes.add(note)
            condition_rows.append(condition_row)
            changed = True
            continue

        if _looks_like_condition_aggregate_row(row):
            changed = True
            continue

        kept_rows.append(row)

    if not changed:
        return [table]

    table["rows"] = kept_rows
    prune_empty_tail_columns(table)

    result = [table]
    if condition_rows:
        result.append(
            {
                "table_id": f"{table.get('table_id', 'table')}-conditions",
                "type": "condition",
                "headers": ["조건", "값", "비고"],
                "rows": condition_rows,
                "notes_in_table": [],
                "raw_row_count": len(condition_rows),
                "parsed_row_count": len(condition_rows),
                "domain": "estimate",
                "role": "condition_table",
            }
        )
    return result


def _has_repeated_long_cell_values(rows: list[Any]) -> bool:
    counter: Counter[str] = Counter()
    for row in rows or []:
        for value in _row_string_values(row):
            normalized = re.sub(r"\s+", " ", value).strip()
            if len(normalized) >= 24 and not _is_numeric(normalized):
                counter[normalized] += 1
    return any(count >= 3 for count in counter.values())


def _status_from_warnings(warnings: list[str]) -> str:
    if "header_row_key_mismatch" in warnings:
        return "fail"
    return "ok" if not warnings else "warning"


def _domain_from_preset(preset: str | None) -> str:
    if preset in {"estimate", "pumsem"}:
        return preset
    return "generic"


def infer_table_contract(
    table: dict[str, Any],
    *,
    preset: str | None = None,
) -> tuple[str, str]:
    """Infer a minimal downstream domain/role contract for non-BOM outputs."""

    explicit_domain = table.get("domain")
    explicit_role = table.get("role")
    if explicit_domain and explicit_role:
        return str(explicit_domain), str(explicit_role)

    table_type = str(table.get("type", ""))
    headers = [str(header) for header in table.get("headers", []) or []]
    compact = _header_compact(headers)
    text = _table_text(table)
    text_compact = _normalize_header(text)

    if explicit_domain == "bom" or table_type in {"BOM_자재", "BOM_LINE_LIST"}:
        role = "line_list_table" if table_type == "BOM_LINE_LIST" else "primary_material_table"
        return "bom", str(explicit_role or role)

    if _is_bom_material_table(headers):
        return "bom", str(explicit_role or "primary_material_table")

    if preset == "pumsem" or table_type in {"A_품셈", "B_규모기준", "C_구분설명"}:
        role_map = {
            "A_품셈": "pumsem_quantity_table",
            "B_규모기준": "pumsem_size_table",
            "C_구분설명": "pumsem_description_table",
        }
        return "pumsem", str(explicit_role or role_map.get(table_type, "pumsem_table"))

    if preset == "estimate":
        if any(keyword in text for keyword in ("일반사항", "특기사항")):
            return "estimate", str(explicit_role or "condition_table")
        has_cost_groups = any(keyword in compact for keyword in ("재료비", "노무비", "경비", "합계"))
        if has_cost_groups and any(keyword in compact for keyword in ("단가", "금액")):
            return "estimate", str(explicit_role or "detail_table")
        if _is_material_quantity_table(headers):
            return "generic", str(explicit_role or "material_quantity_table")
        return "estimate", str(explicit_role or "estimate_table")

    if any(keyword in text for keyword in ("거래명세표", "공급자보관용", "공급받는자", "사업자등록번호")):
        return "trade_statement", str(explicit_role or "trade_statement_table")

    if any(keyword in compact for keyword in ("명칭", "품명", "규격", "단위", "수량", "단가", "금액")):
        hits = sum(1 for keyword in ("명칭", "품명", "규격", "단위", "수량", "단가", "금액") if keyword in compact)
        if hits >= 4:
            return "estimate", str(explicit_role or "estimate_table")

    domain = str(explicit_domain or _domain_from_preset(preset))
    return domain, str(explicit_role or "generic_table")


def _find_qty_unit_shift_columns(headers: list[str]) -> tuple[str, str, str] | None:
    for qty_idx, header in enumerate(headers):
        if not _is_quantity_header(header):
            continue
        unit_idx = qty_idx + 1
        if unit_idx >= len(headers) or not _is_general_unit_header(headers[unit_idx]):
            continue
        for shifted_idx in range(unit_idx + 1, len(headers)):
            if _is_unit_like_header(headers[shifted_idx]):
                return headers[qty_idx], headers[unit_idx], headers[shifted_idx]
    return None


def _looks_like_header_row(row: Any, headers: list[str]) -> bool:
    values = [str(value).strip() for value in _row_values(row, headers) if str(value).strip()]
    if len(values) < 2:
        return False
    header_keys = {_normalize_header(header) for header in headers}
    matches = sum(1 for value in values if _normalize_header(value) in header_keys)
    numeric_count = sum(1 for value in values if _is_numeric(value))
    return matches >= 2 and numeric_count == 0


def validate_bom_table(headers: list[str], rows: list[Any]) -> dict[str, Any]:
    """Return non-mutating quality metadata for a BOM/LINE LIST table."""

    warnings: list[str] = []

    for row in rows:
        if isinstance(row, dict) and list(row.keys()) != headers:
            warnings.append("header_row_key_mismatch")
            break

    if any(_is_self_repeating_composite_header(header) for header in headers):
        warnings.append("self_repeating_composite_header")

    if rows and _looks_like_header_row(rows[0], headers):
        warnings.append("first_row_looks_like_header")

    shifted_columns = _find_qty_unit_shift_columns(headers)
    if shifted_columns:
        qty_key, unit_key, shifted_key = shifted_columns
        for row in rows:
            if not isinstance(row, dict):
                continue
            if (
                not str(row.get(qty_key, "")).strip()
                and _is_numeric(row.get(unit_key, ""))
                and _is_unit_value(row.get(shifted_key, ""))
            ):
                warnings.append("qty_unit_shift_suspected")
                break

    if headers and str(headers[-1]).startswith("Column_"):
        if rows and all(not str(row.get(headers[-1], "")).strip() for row in rows if isinstance(row, dict)):
            warnings.append("empty_tail_column")

    unique_warnings = list(dict.fromkeys(warnings))
    status = "ok" if not unique_warnings else "warning"
    if "header_row_key_mismatch" in unique_warnings:
        status = "fail"
    return {"status": status, "warnings": unique_warnings}


def validate_table_contract(
    headers: list[str],
    rows: list[Any],
    *,
    domain: str = "generic",
    role: str | None = None,
) -> dict[str, Any]:
    """Return minimal quality metadata for a parsed output table."""

    if domain == "bom":
        return validate_bom_table(headers, rows)

    quality = _common_quality(headers, rows)
    warnings = list(quality["warnings"])

    if domain == "estimate" and role == "estimate_table" and headers:
        compact = _header_compact(headers)
        has_quantity = any(keyword in compact for keyword in ("수량", "數量", "QTY", "QUANTITY"))
        has_amount = any(keyword in compact for keyword in ("금액", "金額", "단가", "單價", "AMOUNT", "PRICE"))
        if has_quantity and not has_amount:
            warnings.append("estimate_amount_column_missing")

    if domain == "generic" and _is_estimate_item_table(headers):
        warnings.append("generic_estimate_misroute_suspected")

    if _has_repeated_long_cell_values(rows):
        warnings.append("repeated_long_cell_value")

    unique_warnings = list(dict.fromkeys(warnings))
    return {
        "status": _status_from_warnings(unique_warnings),
        "warnings": unique_warnings,
    }


def annotate_output_contract(
    sections: list[dict[str, Any]],
    *,
    preset: str | None = None,
) -> list[dict[str, Any]]:
    """Attach domain/role/quality fields and remove empty generated tail columns."""

    for section in sections:
        if preset == "estimate":
            normalized_tables: list[dict[str, Any]] = []
            for table in section.get("tables", []) or []:
                if _looks_like_source_info_table(table):
                    normalized_tables.append(_normalize_source_info_table(table))
                else:
                    normalized_tables.extend(_split_estimate_condition_rows(table))
            section["tables"] = normalized_tables

        table_domains: list[str] = []
        table_statuses: list[str] = []
        for table in section.get("tables", []) or []:
            prune_empty_tail_columns(table)
            domain, role = infer_table_contract(table, preset=preset)
            table.setdefault("domain", domain)
            table.setdefault("role", role)
            headers = [str(header) for header in table.get("headers", []) or []]
            rows = table.get("rows", []) or []
            if not isinstance(table.get("quality"), dict):
                table["quality"] = validate_table_contract(
                    headers,
                    rows,
                    domain=str(table.get("domain") or domain),
                    role=str(table.get("role") or role),
                )
            table_domains.append(str(table.get("domain") or domain))
            quality = table.get("quality") or {}
            if isinstance(quality, dict) and quality.get("status"):
                table_statuses.append(str(quality["status"]))

        if "domain" not in section:
            if table_domains and len(set(table_domains)) == 1:
                section["domain"] = table_domains[0]
            else:
                section["domain"] = _domain_from_preset(preset)

        if not isinstance(section.get("quality"), dict):
            if "fail" in table_statuses:
                status = "fail"
            elif "warning" in table_statuses:
                status = "warning"
            else:
                status = "ok"
            section["quality"] = {"status": status, "warnings": []}

    return sections
