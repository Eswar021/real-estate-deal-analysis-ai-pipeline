"""Module 12 — NOI verification (bottom-up vs top-down, per month + total).

The arithmetic gate on the classification: bottom-up = sum DATA rows by assigned
section (capex excluded); top-down = the vendor's locked grand-total rows. Compared
per-month AND on the total; overall_pass requires a match on every month and total.

Ported verbatim from notebook Module 12.
"""
from openpyxl.utils import column_index_from_string

from .cell_grid import grid_row_map, gvalue


def _row_values(grid, row_num, value_cols):
    grow = grid_row_map(grid).get(row_num)
    return [gvalue(grow, c) if grow else None for c in value_cols]


def verify_noi(classified, grid, final_map):
    value_cols = [column_index_from_string(c) for c in final_map["value_columns"]]
    n = len(value_cols)

    # bottom-up (row method) — sum DATA rows by section, capex excluded
    comp_rev = [0.0] * n
    comp_exp = [0.0] * n
    rev_rows, exp_rows = [], []          # which DATA rows fed each section sum (evidence)
    for r in classified:
        if r["class"] != "DATA" or r.get("section") not in ("revenue", "expense"):
            continue
        (rev_rows if r["section"] == "revenue" else exp_rows).append(r["row"])
        for i, v in enumerate(_row_values(grid, r["row"], value_cols)):
            if isinstance(v, (int, float)):
                (comp_rev if r["section"] == "revenue" else comp_exp)[i] += v
    comp_rev = [round(x, 2) for x in comp_rev]
    comp_exp = [round(x, 2) for x in comp_exp]
    # NOI = revenue − expense MAGNITUDE; abs() handles vendors who sign expenses negative
    # (comp_exp comes out negative) as well as those who keep them positive.
    comp_noi = [round(comp_rev[i] - abs(comp_exp[i]), 2) for i in range(n)]

    # top-down (vendor-reported) — the locked grand-total rows
    def _num(vals):
        return [v if isinstance(v, (int, float)) else None for v in vals]
    act_rev = _num(_row_values(grid, final_map["revenue_end_row"], value_cols))
    split = final_map.get("expense_split_rows")
    if split:
        # vendor splits the expense total across >1 row (controllable + non-controllable):
        # the vendor expense per month is their sum, not any single row.
        sums, seen = [0.0] * n, [False] * n
        for er in split:
            for i, v in enumerate(_row_values(grid, er, value_cols)):
                if isinstance(v, (int, float)):
                    sums[i] += v; seen[i] = True
        act_exp = [round(sums[i], 2) if seen[i] else None for i in range(n)]
    else:
        act_exp = _num(_row_values(grid, final_map["expense_end_row"], value_cols))
    act_noi = _num(_row_values(grid, final_map["noi_row"], value_cols))

    def _match(a, c):
        if a is None or c is None:
            return None
        return abs(a - c) <= max(1.0, abs(a) * 0.005)

    months, any_noi_fail = [], False
    for i in range(n):
        noi_ok = _match(act_noi[i], comp_noi[i])
        if noi_ok is False:
            any_noi_fail = True
        months.append({
            "col": final_map["value_columns"][i],
            "rev": (act_rev[i], comp_rev[i], _match(act_rev[i], comp_rev[i])),
            "exp": (act_exp[i], comp_exp[i], _match(act_exp[i], comp_exp[i])),
            "noi": (act_noi[i], comp_noi[i], noi_ok),
        })
    noi_total_ok = months[-1]["noi"][2] if months else None
    return {"months": months, "overall_pass": (noi_total_ok is True) and (not any_noi_fail),
            "revenue_rows": rev_rows, "expense_rows": exp_rows,
            "vendor_rows": {"revenue_end": final_map["revenue_end_row"],
                            "expense_end": final_map["expense_end_row"], "noi": final_map["noi_row"]}}
