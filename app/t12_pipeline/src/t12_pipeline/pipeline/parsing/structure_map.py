"""Structure map — the column layout + boundaries a file is parsed against.

- KNOWN formats: `build_known_map` fills columns from the format's fixed layout (no AI).
- UNKNOWN formats: the AI structure agent proposes the map; `build_final_map` keeps it
  verbatim and adds the arithmetically-validated subsection anchors.

Ported verbatim from notebook Module 8b (+ `build_known_map` from the anchor-lock cell).
"""
from openpyxl.utils import get_column_letter, column_index_from_string

from .cell_grid import grid_row_map, gvalue
from .signals import (detect_value_columns, CODE_COL, DESC_COL,
                      EMB_DESC_COL, NOCODE_DESC_COL)

_MIN_MONTH_COLS = 6


def validate_subsections(final, grid):
    """Arithmetic-check each AI subsection: subtotal == sum of the leaf value rows in
    its [header_row, subtotal_row) span that are NOT themselves subtotal rows.
    Summing only non-subtotal leaves makes this correct for nested roll-ups too.
    Returns (per-subsection results, set of VALIDATED subtotal rows)."""
    last_i = column_index_from_string(final["value_columns"][-1])
    rmap   = grid_row_map(grid)
    def cval(r):
        g = rmap.get(r); x = gvalue(g, last_i) if g else None
        return x if isinstance(x, (int, float)) else None

    subs = final["subsections"]
    subtotal_set = {s["subtotal_row"] for s in subs}
    rev_end = final["revenue_end_row"]; data_start = final["data_start_row"]

    results, validated = [], []
    for s in subs:
        R = s["subtotal_row"]; H = s["header_row"]; target = cval(R)
        # span start: the AI header_row if it sits inside this section, else the section start
        sec_start = data_start if (rev_end is None or R <= rev_end) else rev_end + 1
        start = H if (isinstance(H, int) and sec_start <= H < R) else sec_start
        members = [rr for rr in range(start, R)
                   if rr not in subtotal_set and cval(rr) is not None]
        msum = sum(cval(rr) for rr in members)
        ok = target is not None and abs(msum - target) <= max(1.0, abs(target) * 0.005)
        results.append({"name": s["name"], "row": R, "header_row": H, "span": [start, R],
                        "member_rows": members, "member_values": [round(cval(rr), 2) for rr in members],
                        "members": len(members), "sum": round(msum, 2),
                        "target": round(target, 2) if isinstance(target, (int, float)) else target,
                        "ok": ok})
        if ok:
            validated.append(R)
    return results, sorted(set(validated))


def build_final_map(ai_map, grid):
    """Turn the AI structure map into the final_map used downstream: the AI's fields
    verbatim, PLUS the arithmetically-validated subsection anchors. No deterministic
    override — the AI map is trusted; math only validates the subsections.
    Returns (final_map, per-subsection results)."""
    final = ai_map if isinstance(ai_map, dict) else ai_map.model_dump()
    sub_results, validated_rows = validate_subsections(final, grid)
    boundary = {final["revenue_end_row"], final["expense_end_row"], final["noi_row"]} - {None}
    final["subsection_subtotal_rows"]           = sorted({s["subtotal_row"] for s in final["subsections"]} - boundary)
    final["validated_subsection_subtotal_rows"] = [r for r in validated_rows if r not in boundary]
    final["subsection_header_rows"]             = sorted({s["header_row"] for s in final["subsections"]
                                                          if isinstance(s["header_row"], int)} - boundary)
    return final, sub_results


def _detect_known_layout(grid, value_cols):
    """data_start = first row with >=6 numeric value cells; month_header = the last
    row above it that carries text in the value columns (period labels), else the
    row just above data_start."""
    data_start = None
    for grow in grid["rows"]:
        if sum(1 for c in value_cols if isinstance(gvalue(grow, c), (int, float))) >= _MIN_MONTH_COLS:
            data_start = grow["row"]; break
    month_hdr = None
    for grow in grid["rows"]:
        if data_start and grow["row"] >= data_start:
            break
        if sum(1 for c in value_cols if isinstance(gvalue(grow, c), str) and gvalue(grow, c).strip()) >= _MIN_MONTH_COLS:
            month_hdr = grow["row"]
    if month_hdr is None and data_start:
        month_hdr = data_start - 1
    return month_hdr, data_start


def build_known_map(fmt, grid):
    """A minimal 'template' structure map for a KNOWN format — columns come from the
    format's fixed layout, the layout rows are detected, and the R/E/NOI boundaries are
    left for the anchor lock to fill. Lets known files run the SAME dynamic-extract →
    anchor-lock → classify path as unknown files (no AI structure agent needed)."""
    if fmt == "code_in_a_desc_in_b":
        desc_cols, start = [get_column_letter(DESC_COL)], DESC_COL + 1
        code_col, embedded, pattern = get_column_letter(CODE_COL), False, None
    elif fmt == "embedded_code_in_a":
        desc_cols, start = [get_column_letter(EMB_DESC_COL)], EMB_DESC_COL + 1
        code_col, embedded, pattern = None, True, "embedded"
    else:  # no_code
        desc_cols, start = [get_column_letter(NOCODE_DESC_COL)], NOCODE_DESC_COL + 1
        code_col, embedded, pattern = None, False, None
    value_cols = detect_value_columns(grid, start)
    month_hdr, data_start = _detect_known_layout(grid, value_cols)
    return {
        "description_columns": desc_cols,
        "value_columns": [get_column_letter(c) for c in value_cols],
        "code_column": code_col, "code_embedded_in_description": embedded, "code_pattern": pattern,
        "month_header_row": month_hdr, "data_start_row": data_start,
        "revenue_end_row": None, "expense_end_row": None, "noi_row": None,
        "subsections": [], "validated_subsection_subtotal_rows": [], "subsection_header_rows": [],
    }
