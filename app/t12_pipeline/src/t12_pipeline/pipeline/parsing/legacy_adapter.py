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


