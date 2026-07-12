"""
pages/anchor_gate/helpers.py — page-local helpers.

Builds the context for the Stage-1 anchor gate from the anchor-first pipeline's
anchor_lock.json (candidates + passing triples + status) and the annotated rows
(descriptions + values) so the user can confirm the 3 R / E / NOI anchors.
"""


def int_or_none(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _last_value(r):
    vals = [v for v in (r.get("values") or []) if v is not None]
    return vals[-1] if vals else None


STATUS_EXPLAIN = {
    "AUTO":    ("success", "One R − E = NOI triple passed — anchors auto-locked. Confirm or adjust."),
    "DERIVED": ("warning", "No NOI keyword matched (e.g. a vendor typo); the NOI row was found by arithmetic (N = R − E). Please confirm."),
    "GATE":    ("warning", "Several R − E = NOI triples pass — genuinely ambiguous. Pick the correct three rows."),
    "NONE":    ("danger",  "No triple reconciled. Pick the revenue / expense / NOI rows manually (or the vendor's numbers are inconsistent)."),
}


def build_context(upload, anchor_lock, annotated, comparison, error=None):
    rows = annotated.get("rows", [])
    by = {r["row"]: r for r in rows}

    def info(rn):
        r = by.get(rn) or {}
        return {"row": rn, "description": r.get("description", ""), "value": _last_value(r)}

    cands = anchor_lock.get("candidates") or {}
    candidates = {t: [info(rn) for rn in cands.get(t, [])] for t in ("revenue", "expense", "noi")}

    passing = []
    for trip in anchor_lock.get("passing", []):
        rr, eu, nr = trip[0], trip[1], trip[2]
        eu = eu if isinstance(eu, list) else [eu]
        passing.append({"revenue": rr, "expense": eu, "noi": nr})

    current = {}
    for r in rows:
        if r.get("is_total_revenue"):
            current["revenue_end_row"] = r["row"]
        if r.get("is_total_expense"):
            current["expense_end_row"] = r["row"]
        if r.get("is_noi"):
            current["noi_row"] = r["row"]

    # every value-bearing row — options for the "pick any row" selects
    all_rows = [info(r["row"]) for r in rows if _last_value(r) is not None]

    status = anchor_lock.get("status") or "NONE"
    tone, explain = STATUS_EXPLAIN.get(status, STATUS_EXPLAIN["NONE"])

    return {
        "upload_id":   upload.id,
        "file_name":   annotated.get("file", "") or upload.file_name,
        "status":      status,
        "status_tone": tone,
        "status_explain": explain,
        "reconciles":  comparison.get("overall_pass", False),
        "candidates":  candidates,
        "passing":     passing,
        "current":     current,
        "all_rows":    all_rows,
        "error":       error,
    }
