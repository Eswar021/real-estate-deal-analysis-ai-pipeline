"""
pages/noi_verification/helpers.py — page-local helpers.

Kept colocated with the view so anyone working on this page has all the
relevant code in one folder.

Consumes the symmetric comparison.json shape (see compare_noi.py):
    comparison["overall_pass"]
    comparison["totals"]["revenue" | "expense" | "noi"] = {actual, computed, diff, abs_diff, match}
    comparison["months"][i] = same nested shape
    comparison["tolerance_used"]                 (0 when STRICT, positive otherwise)
"""

FLAG_LABELS = [
    ("is_total_revenue", "Total Revenue", "total_revenue_row"),
    ("is_total_expense", "Total Expense", "total_expense_row"),
    ("is_noi",           "NOI",           "noi_row"),
]


def ui_pass(annotated: dict, comparison: dict) -> bool:
    """
    UI-level pass/fail. Three checks:
      1. NOI match          — overall_pass from pipeline (totals.noi.match + every month.noi.match)
      2. Revenue row check  — totals.revenue.match (depends on is_total_revenue selection)
      3. Expense row check  — flagged is_total_expense row last value ≈ computed expense total
                              (the pipeline's totals.expense.actual is also row-dependent,
                              but we cross-check explicitly to catch the case where the
                              user picked a wrong expense row)

    Threshold for check 3 mirrors the pipeline's STRICT flag, derived from
    comparison["tolerance_used"] == 0 so the two stay in sync automatically.
    """
    if not comparison.get("overall_pass", False):
        return False

    totals = comparison.get("totals") or {}

    rev = totals.get("revenue") or {}
    if rev.get("actual") is not None and rev.get("match") is False:
        return False

    exp = totals.get("expense") or {}
    if exp.get("computed") is not None:
        rows = annotated.get("rows", [])
        flagged = next(
            (r for r in rows if r.get("is_total_expense") and r.get("type") == "subtotal"),
            None,
        )
        if flagged:
            values = [v for v in (flagged.get("values") or []) if v is not None]
            if values:
                row_val   = values[-1]
                comp_val  = exp["computed"]
                diff      = abs(round(row_val, 2) - round(comp_val, 2))
                strict    = comparison.get("tolerance_used", 0) == 0
                threshold = 0 if strict else max(1.0, abs(comp_val) * 0.01)
                if diff > threshold:
                    return False

    return True


def build_context(upload, annotated: dict, comparison: dict, recompute_error: str | None = None) -> dict:
    rows = annotated.get("rows", [])

    def _last_value(r):
        vals = [v for v in (r.get("values") or []) if v is not None]
        return vals[-1] if vals else 0

    all_subtotals = [
        {
            "row":          r["row"],
            "description":  r["description"],
            "total_amount": _last_value(r),
        }
        for r in rows if r.get("type") == "subtotal"
    ]

    key_subtotals = []
    for flag, label, field_name in FLAG_LABELS:
        for r in rows:
            if r.get("type") == "subtotal" and r.get(flag):
                key_subtotals.append({
                    "flag":         flag,
                    "field_name":   field_name,
                    "label":        label,
                    "row":          r["row"],
                    "description":  r["description"],
                    "total_amount": _last_value(r),
                })
                break

    noi_totals = (comparison.get("totals") or {}).get("noi") or {}

    return {
        "upload_id":      upload.id,
        "file_name":      annotated.get("file", "") or upload.file_name,
        "row_count":      len(rows),
        "noi_pass":       ui_pass(annotated, comparison),
        "actual_noi":     noi_totals.get("actual")   or 0,
        "computed_noi":   noi_totals.get("computed") or 0,
        "key_subtotals":  key_subtotals,
        "all_subtotals":  all_subtotals,
        "recompute_error": recompute_error,
    }


def int_or_none(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
