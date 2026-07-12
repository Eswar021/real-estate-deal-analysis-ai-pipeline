"""Natural presentation view of a Stage-2 classification result.

This is the shape the classification-review UI reads directly — the pipeline builds it,
the bridge just persists it, the page renders it (thin bridge: no reshaping in the UI
layer). Unlike `legacy_adapter` (which maps onto the OLD annotated_blocks/comparison
shapes the mapping stage still consumes), this emits the pipeline's own vocabulary:
7-class labels, sections, per-row confidence, and the NOI verification verbatim.
"""
from .classify import LOW_CONFIDENCE_MARGIN
from .legacy_adapter import column_headers


def _cell(triple):
    a, c, m = triple
    return {"actual": a, "computed": c, "match": m}


def build_classification_view(res, file_name=""):
    """Stage-2 result → the classification.json the review page reads."""
    fm = res["final_map"]
    anchors = {
        "revenue_end_row":    fm.get("revenue_end_row"),
        "expense_end_row":    fm.get("expense_end_row"),
        "noi_row":            fm.get("noi_row"),
        "expense_split_rows": fm.get("expense_split_rows"),
    }
    anchor_set = {anchors["revenue_end_row"], anchors["expense_end_row"], anchors["noi_row"],
                  *(anchors["expense_split_rows"] or [])} - {None}

    rows = [{
        "row":            r["row"],
        "description":    r["description"],
        "class":          r["class"],
        "section":        r.get("section"),
        "values":         r.get("values"),
        "confidence":     r.get("confidence"),
        "low_confidence": bool(r.get("low_confidence")),
        "is_anchor":      r["row"] in anchor_set,
    } for r in res["classified"]]

    noi  = res["noi"]
    hdrs = column_headers(res)
    months = [{
        "month":   hdrs[i] if i < len(hdrs) else fm["value_columns"][i],
        "revenue": _cell(m["rev"]), "expense": _cell(m["exp"]), "noi": _cell(m["noi"]),
    } for i, m in enumerate(noi["months"])]
    last = noi["months"][-1] if noi["months"] else None
    totals = {"revenue": _cell(last["rev"]) if last else None,
              "expense": _cell(last["exp"]) if last else None,
              "noi":     _cell(last["noi"]) if last else None}

    fb, diagnosis = res.get("feedback"), None
    if fb:
        dg = fb.get("diagnosis")
        diagnosis = {
            "status":             fb.get("status"),
            "iterations":         fb.get("iterations"),
            "user_message":       getattr(dg, "user_message", None),
            "data_inconsistency": getattr(dg, "data_inconsistency", None),
        }

    return {
        "file":                 file_name,
        "format":               res["format"],
        "anchor_status":        res["anchor_lock"]["status"],
        "anchors":              anchors,
        "column_headers":       hdrs,
        "overall_pass":         noi["overall_pass"],
        "months":               months,
        "totals":               totals,
        "low_confidence_rows":  sorted(res.get("low_confidence_rows", [])),
        "confidence_threshold": LOW_CONFIDENCE_MARGIN,
        "diagnosis":            diagnosis,
        "rows":                 rows,
    }
