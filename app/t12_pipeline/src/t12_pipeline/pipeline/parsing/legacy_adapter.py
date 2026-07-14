"""Mapping-input adapter — build the `annotated_blocks` shape the mapping stage (Stage 3)
consumes from a parse result. The bridge calls `to_annotated` in-memory (no file) to feed
`map_results`; `column_headers` is also reused by the classify step. Pure logic (no Django).
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


def _label(v):
    if hasattr(v, "strftime"):          # a real date cell → "Apr 2026"
        return v.strftime("%b %Y")
    return str(v).strip() if v not in (None, "") else ""


def column_headers(res):
    """The month/period header labels. Handles MULTI-ROW headers (e.g. Mirador's
    'Month Ending' / date / 'Actual' stack) by joining every header-band row per column —
    the band is the contiguous text rows ending at month_header_row. Single-row headers are
    unchanged. Falls back to the value-column letter when a column has no header text."""
    fm = res["final_map"]; grid = res["cell_grid"]; rmap = grid_row_map(grid)
    mh = fm.get("month_header_row")
    value_cols = [column_index_from_string(c) for c in fm["value_columns"]]
    if not mh:
        return list(fm["value_columns"])
    band, r = [], mh                     # walk up while rows carry text in the value columns
    while r >= 1:
        grow = rmap.get(r)
        if not (grow and any(isinstance(gvalue(grow, c), str) and gvalue(grow, c).strip() for c in value_cols)):
            break
        band.append(grow); r -= 1
    band.reverse()                       # top-to-bottom reading order
    out = []
    for c, letter in zip(value_cols, fm["value_columns"]):
        parts = [_label(gvalue(grow, c)) for grow in band]
        parts = [p for p in parts if p]
        out.append(" ".join(parts) if parts else letter)
    return out


def res_from_state(state):
    """Run-state → the flat `res` shape `to_annotated` consumes. Lives here (not in the UI
    bridge) so Stage 3 is runnable without Django."""
    cls = state["classification"]
    return {"format": state["format"]["format"], "final_map": state["structure_map"],
            "cell_grid": state["cell_grid"], "anchor_lock": state["anchor_lock"],
            "classified": cls["classified"], "noi": cls["noi"], "feedback": None,
            "signal_rows": state["signals"], "low_confidence_rows": cls["low_confidence_rows"]}


def to_annotated(res, file_name="", file_path=""):
    """parse_file result → legacy annotated_blocks dict (what the mapping stage reads).
    The anchor flags come straight from the LOCKED anchors in final_map (= structure_map after
    the gate's picks are applied), so Stage 3 maps against the same rows the user confirmed."""
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


