"""Module 10 — Normalized signal-match classifier (7 classes).

UNBIASED scoring: no hand-tuned weights. Each class lists the signals it should
satisfy (CLASS_SIGNALS); a row's score for a class = the FRACTION of that class's
signals it satisfies. argmax wins; normalising by the signal count lets classes with
different signal counts compare fairly. Contra-indicators are positive signals
(not_subtotal_marked, not_metric). The AI subsection anchors are NOT scored here —
they are facts for the override layer.

`confidence` (top score − runner-up) is added per row for the confidence gate.
Ported verbatim from notebook Module 10 (print helpers dropped).
"""
from openpyxl.utils import column_index_from_string

from .cell_grid import grid_row_map, gvalue

CLASSES = ["METADATA", "SECTION_HEADER", "SUBSECTION_HEADER", "DATA",
           "SUBSECTION_SUBTOTAL", "SECTION_SUBTOTAL", "COMPUTED_METRIC"]

# WHICH signals each class considers (config). DESIGN RULE: a class lists only signals
# that are RELIABLY true for it. `subtotal_marked` (bold OR a "Total" keyword) is the
# reliable "this row is a total" cue — folding both into one signal stops a single-cue
# subtotal from being diluted to a low fraction.
CLASS_SIGNALS = {
    "METADATA":            ["no_values", "in_metadata_band", "no_total_keyword"],
    "SECTION_HEADER":      ["no_values", "in_body", "bold_or_caps", "shallow"],
    "SUBSECTION_HEADER":   ["no_values", "in_body", "is_bold", "deep"],
    "DATA":                ["has_values", "not_subtotal_marked", "not_metric"],
    "SUBSECTION_SUBTOTAL": ["has_values", "in_body", "subtotal_marked",
                            "not_metric", "not_all_caps"],
    "SECTION_SUBTOTAL":    ["has_values", "subtotal_marked", "all_caps", "not_metric"],
    "COMPUTED_METRIC":     ["has_values", "in_body", "is_metric"],
}

# HOW each signal name is evaluated on a feature-vector row (config). Negated and
# derived signals live here, so the extractor only stores raw booleans.
SIGNAL_FUNCS = {
    "has_values":              lambda r: bool(r["has_values"]),
    "no_values":               lambda r: not r["has_values"],
    "is_bold":                 lambda r: bool(r["is_bold"]),
    "not_bold":                lambda r: not r["is_bold"],
    "all_caps":                lambda r: bool(r["all_caps"]),
    "not_all_caps":            lambda r: not r["all_caps"],
    "bold_or_caps":            lambda r: bool(r["is_bold"] or r["all_caps"]),
    "total_keyword":           lambda r: bool(r["total_keyword"]),
    "no_total_keyword":        lambda r: not r["total_keyword"],
    "subtotal_marked":         lambda r: bool(r["is_bold"] or r["total_keyword"]),
    "not_subtotal_marked":     lambda r: not (r["is_bold"] or r["total_keyword"]),
    "is_metric":               lambda r: bool(r["is_metric"]),
    "not_metric":              lambda r: not r["is_metric"],
    "arithmetic_sum_of_above": lambda r: bool(r.get("arithmetic_sum_of_above")),
    "no_arithmetic":           lambda r: not r.get("arithmetic_sum_of_above"),
    "has_formula":             lambda r: bool(r["has_formula"]),
    "top_border":              lambda r: bool(r["top_border"]),
    "no_top_border":           lambda r: not r["top_border"],
    "deep":                    lambda r: r["column_depth"] >= 2 or r["whitespace_depth"] >= 2,
    "shallow":                 lambda r: r["column_depth"] <= 1 and r["whitespace_depth"] < 2,
    "in_metadata_band":        lambda r: bool(r.get("in_metadata_band")),
    "in_body":                 lambda r: not r.get("in_metadata_band"),
}


def score_row(f):
    """Score against all 7 classes = fraction of each class's signals satisfied.
    Unbiased: every signal counts 1; normalised by the class's signal count."""
    return {cls: round(sum(SIGNAL_FUNCS[s](f) for s in sigs) / len(sigs), 3)
            for cls, sigs in CLASS_SIGNALS.items()}


def classify_rows(rows, structure_map=None):
    """Attach `class` (argmax of the normalised fractions), `scores`, and `confidence`
    (top score − runner-up) to each row. structure_map is accepted for call-site
    compatibility but unused — every signal is already baked into the feature vector.
    Ties break toward the earlier class in CLASSES (dict-insertion order)."""
    out = []
    for f in rows:
        sc = score_row(f)
        best = max(sc, key=sc.get)
        ranked = sorted(sc.values(), reverse=True)
        confidence = round(ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0), 3)
        out.append({**f, "class": best, "scores": sc, "confidence": confidence})
    return out


def reconcile_leaf_data(rows, grid, structure_map):
    """Correctness self-check: the values of ONLY the DATA-class rows in each section
    must sum to that section's grand total. Returns computed vs vendor + the rows."""
    last  = column_index_from_string(structure_map["value_columns"][-1])
    rmap  = grid_row_map(grid)
    def v(r):
        g = rmap.get(r); x = gvalue(g, last) if g else None
        return x if isinstance(x, (int, float)) else 0.0
    mh, rev_end, exp_end, noi_r = (structure_map["month_header_row"], structure_map["revenue_end_row"],
                                   structure_map["expense_end_row"], structure_map["noi_row"])
    rev_rows = [r["row"] for r in rows if r["class"] == "DATA" and mh < r["row"] < rev_end]
    exp_rows = [r["row"] for r in rows if r["class"] == "DATA" and rev_end < r["row"] < exp_end]
    rev = sum(v(rr) for rr in rev_rows); exp = sum(v(rr) for rr in exp_rows)
    ok = lambda a, b: abs(a - b) <= max(1.0, abs(b) * 0.005)
    return {
        "revenue": {"computed": round(rev, 2), "vendor": round(v(rev_end), 2),
                    "ok": ok(rev, v(rev_end)), "rows": rev_rows, "n": len(rev_rows)},
        "expense": {"computed": round(exp, 2), "vendor": round(v(exp_end), 2),
                    "ok": ok(exp, v(exp_end)), "rows": exp_rows, "n": len(exp_rows)},
        "noi":     {"computed": round(rev - exp, 2), "vendor": round(v(noi_r), 2),
                    "ok": ok(rev - exp, v(noi_r))},
    }
