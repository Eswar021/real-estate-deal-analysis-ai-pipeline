"""Compatibility layer — map the anchor-first `parse_file` result onto the legacy
`annotated_blocks` / `comparison` / `actual_noi` shapes the Django UI and the mapping
stage (Stage 3) already consume. Lets the bridge swap its guts without rewriting the
mapping stage or the UI data contracts.

Pure logic (no Django) so it's unit-testable.
"""
from openpyxl.utils import column_index_from_string

from .cell_grid import grid_row_map, gvalue

# classifier class → legacy `type`
_TYPE = {
    "DATA": "data",
    "SUBSECTION_SUBTOTAL": "subtotal", "SECTION_SUBTOTAL": "subtotal",
    "COMPUTED_METRIC": "subtotal",
    "SECTION_HEADER": "header", "SUBSECTION_HEADER": "header",
    "METADATA": "empty",
}


def column_headers(res):
    """The month/period header labels, from the month_header_row (falls back to the
    value-column letters)."""
    fm = res["final_map"]; grid = res["cell_grid"]; mh = fm.get("month_header_row")
    grow = grid_row_map(grid).get(mh) if mh else None
    out = []
    for letter in fm["value_columns"]:
        v = gvalue(grow, column_index_from_string(letter)) if grow else None
        out.append(str(v).strip() if v not in (None, "") else letter)
    return out


def to_annotated(res, file_name="", file_path=""):
    """parse_file result → legacy annotated_blocks dict (what the mapping stage reads)."""
    fm = res["final_map"]
    rev_end, exp_end, noi_row = fm.get("revenue_end_row"), fm.get("expense_end_row"), fm.get("noi_row")
    rows_out, stack = [], []          # stack = [section_header, subsection_header]
    for r in res["classified"]:
        cls = r["class"]; typ = _TYPE.get(cls, "data")
        if cls == "SECTION_HEADER":
            stack = [r["description"]]
        elif cls == "SUBSECTION_HEADER":
            stack = (stack[:1] if stack else []) + [r["description"]]
        row_out = {
            "row": r["row"], "type": typ, "description": r["description"],
            "section_context": stack[-1] if stack else "",
            "section_path": list(stack),
            "is_total_revenue": r["row"] == rev_end,
            "is_total_expense": r["row"] == exp_end,
            "is_noi": r["row"] == noi_row,
        }
        if typ in ("data", "subtotal"):
            row_out["statement_side"] = r.get("section")
            row_out["values"] = r.get("values")
        rows_out.append(row_out)

    data_rows = sum(1 for r in rows_out if r["type"] == "data")
    return {
        "file": file_name, "file_path": file_path, "format": res["format"],
        "data_start_row": fm.get("data_start_row"),
        "column_headers": column_headers(res),
        "summary": {"total_rows": len(rows_out), "data_rows": data_rows,
                    "anchor_status": res["anchor_lock"]["status"]},
        "rows": rows_out,
    }


def _blk(actual, computed):
    if actual is None or computed is None:
        return {"actual": actual, "computed": computed, "diff": None, "abs_diff": None, "match": None}
    diff = round(computed - actual, 2)
    return {"actual": round(actual, 2), "computed": round(computed, 2), "diff": diff,
            "abs_diff": round(abs(diff), 2), "match": abs(diff) <= max(1.0, abs(actual) * 0.005)}


def to_comparison(res, file_name=""):
    """parse_file result → legacy comparison dict (what the noi_verification page shows).
    Built directly from the anchor-first NOI verification."""
    noi = res["noi"]; hdrs = column_headers(res)
    months = []
    for i, m in enumerate(noi["months"]):
        months.append({
            "month":   hdrs[i] if i < len(hdrs) else res["final_map"]["value_columns"][i],
            "revenue": _blk(m["rev"][0], m["rev"][1]),
            "expense": _blk(m["exp"][0], m["exp"][1]),
            "noi":     _blk(m["noi"][0], m["noi"][1]),
        })
    last = noi["months"][-1] if noi["months"] else None
    totals = {
        "revenue": _blk(last["rev"][0], last["rev"][1]) if last else _blk(None, None),
        "expense": _blk(last["exp"][0], last["exp"][1]) if last else _blk(None, None),
        "noi":     _blk(last["noi"][0], last["noi"][1]) if last else _blk(None, None),
    }
    noi_desc = next((r["description"] for r in res["classified"]
                     if r["row"] == res["final_map"].get("noi_row")), "")
    return {
        "file": file_name, "format": res["format"], "column_headers": hdrs,
        "overall_pass": noi["overall_pass"], "tolerance_used": "max($1, 0.5%)",
        "months": months, "totals": totals,
        "actual_noi_row": noi_desc, "skipped_count": 0, "unmapped_count": 0,
        "anchor_status": res["anchor_lock"]["status"],
    }


def to_actual_noi(res):
    """Minimal vendor-totals view (the data_review page reads this)."""
    noi = res["noi"]; last = noi["months"][-1] if noi["months"] else None
    return {
        "format": res["format"],
        "revenue_end_row": res["final_map"].get("revenue_end_row"),
        "expense_end_row": res["final_map"].get("expense_end_row"),
        "noi_row": res["final_map"].get("noi_row"),
        "noi": {"actual": last["noi"][0] if last else None,
                "description": to_comparison(res)["actual_noi_row"]},
    }
