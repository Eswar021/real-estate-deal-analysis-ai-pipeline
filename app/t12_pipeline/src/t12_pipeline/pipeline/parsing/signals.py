"""Low-level per-row signal primitives — keyword/metric predicates, value-column
detection (unknown formats), and the arithmetic sum-of-above check.

Ported from notebook Modules 5 and 9. (Known-format columns now live in
`config/known_formats.json`; the hardcoded column constants + `detect_value_columns`
first-run helper were retired when `build_known_map` became config-driven.)
"""
import re

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


def detect_value_block(grid, min_hits=5, min_len=6):
    """Value columns for an UNKNOWN layout — the LONGEST contiguous run of numeric-dense
    columns (the monthly block + trailing total). Scans ALL columns; unlike
    `detect_value_columns` (first run from a KNOWN start column), taking the *longest* run
    ignores stray numeric columns — e.g. a hierarchical file whose subtotals bleed numbers
    into an early description column (Cardinal's col A) — because those form a short run while
    the 12-month block is long. Requires >= `min_len` columns so a stray pair never wins.
    Returns the 1-based column indices, or [] if no block qualifies."""
    numeric = {}
    for grow in grid["rows"]:
        for c, cell in grow["cells"].items():
            if isinstance(cell["value"], (int, float)):
                numeric[c] = numeric.get(c, 0) + 1
    dense = sorted(c for c, n in numeric.items() if n >= min_hits)
    if not dense:
        return []
    best, cur = [], [dense[0]]
    for c in dense[1:]:
        if c == cur[-1] + 1:
            cur.append(c)
        else:
            if len(cur) > len(best):
                best = cur
            cur = [c]
    if len(cur) > len(best):
        best = cur
    if len(best) < min_len:
        return []
    # trim END columns far sparser than the block's core — a stray trailing column with a
    # handful of numbers and no month header (Crystal Lake col P: 5 cells vs the months' 222)
    # would otherwise become the "total" column and break the NOI total check.
    thr = 0.25 * max(numeric[c] for c in best)
    while len(best) > min_len and numeric[best[-1]] < thr:
        best = best[:-1]
    while len(best) > min_len and numeric[best[0]] < thr:
        best = best[1:]
    return best


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
        # A real subtotal equals its members EXACTLY; a tiny $1 slack covers penny/dollar
        # rounding only. NO percentage tolerance here — this is the sole evidence that an
        # unmarked row is a subtotal, so it must be near-exact. A % slack scales with the
        # value ($100 on a $20k row) and lets unrelated lines coincidentally "sum" to it
        # (e.g. Cardinal row 30, off by $37) — a phantom subtotal that then drops real
        # revenue from the NOI. Across the sample every genuine subtotal reconciles within $1.
        tol = 1.0 if isinstance(target, (int, float)) else None
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
