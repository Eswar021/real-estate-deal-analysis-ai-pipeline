"""Low-level per-row signal primitives — keyword/metric predicates, value-column
detection, and the arithmetic sum-of-above check.

Ported verbatim from notebook Modules 5 and 9. The known-format description-column
constants are the fixed layouts `build_known_map` uses.
"""
import re

# ── known-format description / code columns (1-based) ─────────────────────────
CODE_COL, DESC_COL = 1, 2   # code_in_a_desc_in_b: code in A, description in B, values from C
EMB_DESC_COL       = 1      # embedded_code_in_a: code embedded in the description in A
NOCODE_DESC_COL    = 1      # no_code: description in A

TOTAL_KEYWORDS = [
    "net operating income", "effective gross income", "net rental revenue", "net rental income",
    "net income", "net rent revenue", "net cash flow", "collectible rental revenue",
    "adjusted gross possible rental revenue", "total net rent", "total income", "total revenue",
    "total expenses", "total operating expenses", "total operating revenues", "taxable income",
    "income after debt service",
]

# COMPUTED_METRIC keyword pool — a figure computed ACROSS sections (revenue − expense).
METRIC_KEYWORDS = ["net operating income", "noi", "net cash flow",
                   "income after debt service", "cash flow after"]


def has_total_keyword(desc):
    d = desc.strip().lower()
    if d.startswith("total ") or d == "total":
        return True
    return any(re.search(r"\b" + re.escape(kw) + r"\b", d) for kw in TOTAL_KEYWORDS)


def total_keyword_hit(desc):
    """The specific total-keyword that fired — for evidence/logging — or None."""
    d = desc.strip().lower()
    if d.startswith("total ") or d == "total":
        return "total*"
    return next((kw for kw in TOTAL_KEYWORDS if re.search(r"\b" + re.escape(kw) + r"\b", d)), None)


def is_metric(desc):
    d = (desc or "").strip().lower()
    return any(k in d for k in METRIC_KEYWORDS)


def detect_value_columns(grid, start_col, min_hits=5):
    """Columns at/after start_col that hold numbers in enough rows = the value region.
    Reads cell_grid. Returns only the FIRST CONTIGUOUS run: the 12 months + total sit in
    adjacent columns, so a second numeric block further right (e.g. a duplicate embedded
    'Income Statement' table, seen in some RealPage exports) is correctly excluded — it
    starts after a column gap and would otherwise inflate every downstream sum."""
    numeric = {}
    for grow in grid["rows"]:
        for c, cell in grow["cells"].items():
            if c >= start_col and isinstance(cell["value"], (int, float)):
                numeric[c] = numeric.get(c, 0) + 1
    cols = sorted(c for c, n in numeric.items() if n >= min_hits)
    if not cols:
        return []
    run = [cols[0]]
    for c in cols[1:]:
        if c != run[-1] + 1:
            break
        run.append(c)
    return run


def apply_arithmetic(rows):
    """Pass 2 — arithmetic_sum_of_above. Provisional data = has values and no
    'Total' keyword; a row scores True if its value equals the sum of the
    consecutive provisional-data rows directly above it. Format-agnostic.
    Also records the full evidence on row['arithmetic'] (which rows were summed,
    their values, the sum, the target, the diff and tolerance) so a Y/N can always
    be explained — e.g. 'row 21 = Σ rows 12..20 = 100,800 vs target 100,800 ✓'."""
    for row in rows:
        row["_prov_data"] = row["has_values"] and not row["total_keyword"]
    for i, row in enumerate(rows):
        target, match = row["_last_value"], False
        member_rows, member_vals, s, j = [], [], 0.0, i - 1
        while j >= 0 and rows[j]["_prov_data"]:
            v = rows[j]["_last_value"]
            if v is not None:
                s += v; member_rows.append(rows[j]["row"]); member_vals.append(round(v, 2))
            j -= 1
        tol = max(1.0, abs(target) * 0.005) if isinstance(target, (int, float)) else None
        if isinstance(target, (int, float)) and member_rows:
            match = abs(s - target) <= tol
        row["arithmetic_sum_of_above"] = match
        row["arithmetic"] = {
            "fired":         match,
            "member_rows":   member_rows[::-1],   # top-to-bottom order
            "member_values": member_vals[::-1],
            "sum":           round(s, 2) if member_rows else None,
            "target":        round(target, 2) if isinstance(target, (int, float)) else None,
            "diff":          round(abs(s - target), 2) if (isinstance(target, (int, float)) and member_rows) else None,
            "tolerance":     round(tol, 2) if tol is not None else None,
        }
