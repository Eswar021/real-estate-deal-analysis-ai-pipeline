"""
pages/data_review/helpers.py — page-local helpers for the Map Categories page.

Three responsibilities:
  - effective_mapping_of(row)  — which category to display for a row
  - build_table_rows()         — per-row dict the template iterates over
  - compute_summary()          — bottom rows: Net Rental Income / Calculated NOI / Original NOI / NOI Difference
"""

from t12_mapping import pipeline_bridge


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


def compute_summary(mapped_data: dict, actual_noi: dict) -> dict:
    """
    Bottom summary rows. All use the same statement_side semantics as Stage 1:
      revenue add, expense subtract, capex skipped (excluded from NOI).
    Flip-sign is applied per row.
    """
    column_headers = mapped_data.get("column_headers", [])
    n = len(column_headers)

    rev_by_month  = [0.0] * n
    exp_by_month  = [0.0] * n

    for r in mapped_data.get("rows", []):
        if r.get("type") != "data":
            continue
        side = r.get("statement_side")
        if side not in ("revenue", "expense"):
            continue
        for i, v in enumerate(_signed_values(r)[:n]):
            if not isinstance(v, (int, float)):
                continue
            if side == "revenue":
                rev_by_month[i] += v
            else:
                exp_by_month[i] += v

    rev_by_month = [round(v, 2) for v in rev_by_month]
    exp_by_month = [round(v, 2) for v in exp_by_month]
    calc_noi     = [round(rev_by_month[i] - exp_by_month[i], 2) for i in range(n)]

    actual_noi_block = (actual_noi.get("noi") or {})
    actual_noi_by_month = actual_noi_block.get("by_month") or [None] * n
    actual_noi_by_month = [v if isinstance(v, (int, float)) else None for v in actual_noi_by_month][:n]
    actual_noi_by_month += [None] * (n - len(actual_noi_by_month))

    # A difference is only real if it clears the pipeline's NOI tolerance — the SAME rule
    # Stage 2 passed the file on. Testing != 0 flagged the few cents of vendor rounding drift
    # that survive a 100+ row sum, painting the page red under a column of zeros.
    diff_by_month = [
        {"value": round(calc_noi[i] - actual_noi_by_month[i], 2),
         "material": abs(calc_noi[i] - actual_noi_by_month[i]) > pipeline_bridge.NOI_TOLERANCE}
        if actual_noi_by_month[i] is not None else {"value": None, "material": False}
        for i in range(n)
    ]

    return {
        "column_headers":         column_headers,
        "net_rental_income":      rev_by_month,
        "calculated_noi":         calc_noi,
        "original_noi":           actual_noi_by_month,
        "noi_difference":         diff_by_month,
        "any_diff_material":      any(d["material"] for d in diff_by_month),
    }
