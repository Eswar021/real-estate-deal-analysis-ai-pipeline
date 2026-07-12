"""
pages/noi_verification/helpers.py — page-local presenter + context for the classification review.

Phase D: this page reads the run-state directly (no classification.json, no bridge reshaping).
`build_view` is the page-local presenter — it turns the run-state's classification slice + the
confirmed anchors into the review view (needs no cell_grid; column_headers were computed at
classify time). `build_context` then shapes that view for the template.
"""

SECTION_ORDER = [
    ("revenue", "Revenue"),
    ("expense", "Expense"),
    ("capex",   "Capex / below NOI"),
    ("metadata", "Metadata"),
]


def int_or_none(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _last(values):
    vals = [v for v in (values or []) if v is not None]
    return vals[-1] if vals else None


def _cell(triple):
    a, c, m = triple
    return {"actual": a, "computed": c, "match": m}


def build_view(state: dict) -> dict:
    """Run-state → the classification review view (page-local presenter)."""
    cls = state["classification"]
    fm  = state["structure_map"]
    anchors = {"revenue_end_row":    fm.get("revenue_end_row"),
               "expense_end_row":    fm.get("expense_end_row"),
               "noi_row":            fm.get("noi_row"),
               "expense_split_rows": fm.get("expense_split_rows")}
    anchor_set = {anchors["revenue_end_row"], anchors["expense_end_row"], anchors["noi_row"],
                  *(anchors["expense_split_rows"] or [])} - {None}

    rows = [{"row": r["row"], "description": r["description"], "class": r["class"],
             "section": r.get("section"), "values": r.get("values"),
             "confidence": r.get("confidence"), "low_confidence": bool(r.get("low_confidence")),
             "is_anchor": r["row"] in anchor_set}
            for r in cls["classified"]]

    noi  = cls["noi"]
    hdrs = cls.get("column_headers", [])
    months = [{"month":   hdrs[i] if i < len(hdrs) else fm["value_columns"][i],
               "revenue": _cell(m["rev"]), "expense": _cell(m["exp"]), "noi": _cell(m["noi"])}
              for i, m in enumerate(noi["months"])]
    last = noi["months"][-1] if noi["months"] else None
    totals = {"revenue": _cell(last["rev"]) if last else None,
              "expense": _cell(last["exp"]) if last else None,
              "noi":     _cell(last["noi"]) if last else None}

    return {
        "file":                 state["file"]["name"],
        "format":               state["format"]["format"],
        "anchor_status":        (state.get("anchor_lock") or {}).get("status"),
        "anchors":              anchors,
        "overall_pass":         noi["overall_pass"],
        "months":               months,
        "totals":               totals,
        "low_confidence_rows":  sorted(cls.get("low_confidence_rows", [])),
        "confidence_threshold": cls.get("confidence_threshold"),
        "diagnosis":            cls.get("diagnosis"),
        "rows":                 rows,
    }


def ui_pass(view: dict) -> bool:
    """Green only when NOI reconciles AND the revenue and expense totals both match — two
    green lights, since a net NOI check alone can hide compensating misclassifications."""
    if not view.get("overall_pass"):
        return False
    for side in ("revenue", "expense"):
        t = (view.get("totals") or {}).get(side) or {}
        if t.get("actual") is not None and t.get("match") is False:
            return False
    return True


def build_context(upload, state: dict, recompute_error: str | None = None) -> dict:
    view = build_view(state)
    rows = view["rows"]

    by_section = {}
    for r in rows:
        by_section.setdefault(r.get("section") or "metadata", []).append({
            "row":            r["row"],
            "description":    r["description"],
            "class":          r["class"],
            "total":          _last(r.get("values")),
            "confidence":     r.get("confidence"),
            "low_confidence": r.get("low_confidence"),
            "is_anchor":      r.get("is_anchor"),
        })
    sections = [{"name": n, "label": lbl, "rows": by_section[n]}
                for n, lbl in SECTION_ORDER if by_section.get(n)]

    all_rows = [{"row": r["row"], "description": r["description"], "value": _last(r.get("values"))}
                for r in rows if _last(r.get("values")) is not None]

    totals  = view.get("totals") or {}
    anchors = view.get("anchors") or {}
    totals_cards = [
        {"label": lbl, "actual": (totals.get(k) or {}).get("actual"),
         "computed": (totals.get(k) or {}).get("computed"), "match": (totals.get(k) or {}).get("match")}
        for k, lbl in (("revenue", "Revenue"), ("expense", "Expense"), ("noi", "NOI"))
    ]
    anchor_selects = [
        {"label": "Revenue grand total (R)",    "name": "total_revenue_row", "current": anchors.get("revenue_end_row")},
        {"label": "Expense grand total (E)",    "name": "total_expense_row", "current": anchors.get("expense_end_row")},
        {"label": "Net Operating Income (NOI)", "name": "noi_row",           "current": anchors.get("noi_row")},
    ]
    return {
        "upload_id":       upload.id,
        "file_name":       view.get("file", "") or upload.file_name,
        "row_count":       len(rows),
        "noi_pass":        ui_pass(view),
        "overall_pass":    view.get("overall_pass"),
        "months":          view.get("months", []),
        "totals_cards":    totals_cards,
        "sections":        sections,
        "low_conf_count":  len(view.get("low_confidence_rows") or []),
        "anchor_selects":  anchor_selects,
        "all_rows":        all_rows,
        "diagnosis":       view.get("diagnosis"),
        "recompute_error": recompute_error,
    }
