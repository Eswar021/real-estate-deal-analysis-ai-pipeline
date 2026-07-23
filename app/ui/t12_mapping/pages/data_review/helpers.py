"""
pages/data_review/helpers.py — page-local helpers for the Map Categories page.

Three responsibilities:
  - effective_mapping_of(row)  — which category to display for a row
  - build_table_rows()         — per-row dict the template iterates over
  - compute_summary()          — bottom rows: Net Rental Income / Calculated NOI / Original NOI / NOI Difference
"""


def effective_mapping_of(row: dict) -> str | None:
    """User override → rulebook hit → AI suggestion → None."""
    return (
        row.get("final_mapping")
        or row.get("mapping")
        or row.get("ai_suggested_mapping")
    )


def _row_type_label(r: dict) -> str | None:
    """Human label for the row's structural type. None for data rows."""
    row_type = r.get("type")
    if row_type == "header":
        return "Header"
    if row_type == "subtotal":
        if r.get("is_total_revenue"):
            return "Total Revenue"
        if r.get("is_total_expense"):
            return "Total Expense"
        if r.get("is_noi"):
            return "NOI"
        return "Subtotal"
    return None


def _signed_values(row: dict) -> list:
    """Row values with flip_sign applied if True."""
    values = row.get("values") or []
    if row.get("flip_sign"):
        return [-v if isinstance(v, (int, float)) else v for v in values]
    return values


def mapping_stats(rows: list[dict]) -> dict:
    """Counts for the header banner — how the Stage-3 mapping landed, over the DATA rows only.
    `mapped` = has an effective category (rulebook, AI suggestion, or user override);
    `unmapped` = none yet (needs a manual pick); `ai_suggested` = category came from the AI
    fallback, not the rulebook (worth a glance)."""
    data = [r for r in rows if r.get("is_data")]
    unmapped = sum(1 for r in data if r.get("is_unmapped"))
    return {
        "total":        len(data),
        "mapped":       len(data) - unmapped,
        "unmapped":     unmapped,
        "ai_suggested": sum(1 for r in data if r.get("is_ai_only")),
    }


def build_table_rows(mapped_data: dict) -> list[dict]:
    """
    One entry per non-empty row (data + subtotal + header).

    Data rows get the full mapping/flip-sign/override metadata.
    Non-data rows get a type_label ("Header" / "Subtotal" / "Total Revenue" /
    "Total Expense" / "NOI") and their values, but no mapping fields — they
    aren't user-categorizable.
    """
    rows_out = []
    for r in mapped_data.get("rows", []):
        row_type = r.get("type")
        if row_type == "empty":
            continue

        is_data           = row_type == "data"
        is_subtotal       = row_type == "subtotal"
        is_final_subtotal = is_subtotal and (
            r.get("is_total_revenue") or r.get("is_total_expense") or r.get("is_noi")
        )

        rows_out.append({
            "row":               r["row"],
            "description":       r.get("description", ""),
            "type":              row_type,
            "type_label":        _row_type_label(r),
            "is_data":           is_data,
            "is_header":         row_type == "header",
            "is_subtotal":       is_subtotal,
            "is_final_subtotal": bool(is_final_subtotal),
            "section_context":   r.get("section_context", ""),
            "statement_side":    r.get("statement_side"),
            "effective_mapping": effective_mapping_of(r) if is_data else None,
            "original_mapping":  (r.get("mapping") or r.get("ai_suggested_mapping")) if is_data else None,
            "flip_sign":         bool(r.get("flip_sign")) if is_data else False,
            "values":            _signed_values(r),
            "ai_suggested":      r.get("ai_suggested_mapping") if is_data else None,
            "ai_confidence":     r.get("ai_confidence") if is_data else None,
            "is_user_override":  is_data and (r.get("final_mapping") is not None),
            "is_ai_only":        is_data and (r.get("mapping") is None) and (r.get("ai_suggested_mapping") is not None),
            "is_unmapped":       is_data and effective_mapping_of(r) is None,
        })
    return rows_out


def compute_summary(noi_months: list[dict], column_headers: list) -> dict:
    """
    Bottom summary rows, read straight from Stage 2's verified NOI result: the same numbers,
    and the same per-month pass/fail, that the classification gate showed.

    The page does NOT re-derive them. It used to sum the mapped rows itself, which was a second
    implementation of a question the pipeline had already answered — and it drifted: it summed
    `revenue - expense` where the pipeline sums `revenue - |expense|`, so a vendor who signs
    expenses negative (Chateau in the Woods) showed a $730k difference on a file Stage 2 had
    passed. Mapping only assigns categories; it cannot move the money, so there is nothing here
    for a second opinion to catch.

    Each month of `noi_months` is {"rev"/"exp"/"noi": (vendor_actual, our_computed, match)}.
    """
    net_rental_income = [m["rev"][1] for m in noi_months]
    calculated_noi    = [m["noi"][1] for m in noi_months]
    original_noi      = [m["noi"][0] for m in noi_months]

    diff_by_month = []
    for m in noi_months:
        actual, computed, match = m["noi"]
        if actual is None or computed is None:
            diff_by_month.append({"value": None, "material": False})
        else:
            diff_by_month.append({"value": round(computed - actual, 2), "material": match is False})

    return {
        "column_headers":         column_headers,
        "net_rental_income":      net_rental_income,
        "calculated_noi":         calculated_noi,
        "original_noi":           original_noi,
        "noi_difference":         diff_by_month,
        "any_diff_material":      any(d["material"] for d in diff_by_month),
    }
