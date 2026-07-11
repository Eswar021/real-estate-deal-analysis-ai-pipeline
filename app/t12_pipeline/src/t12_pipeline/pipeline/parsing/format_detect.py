"""Module 4 — Format detection (scoring-based, reads cell_grid).

Position-agnostic per-column signal scoring over the first ~60 rows: high score for a
known format → route to its template map; low / no score → 'unknown' (AI structure
agent). Ported verbatim from notebook Module 4.
"""
import re

from .cell_grid import grid_row_map, gvalue

PURE_CODE      = re.compile(r"^\d{4}-\d{2,4}$")             # 4350-0000  (whole cell)
EMBEDDED_CODE  = re.compile(r"^\s*\d{4}\s*-\s*\d*\s*-?\s*")  # 5120 - Desc (code prefix)
EMBEDDED_STRIP = r"^\s*\d{4}\s*-\s*\d*\s*-?\s*"             # strip prefix to test for text
FOREIGN_CODES = {
    "dot":    re.compile(r"^\s*\d{4}\.\d"),      # 5120.0000     Cardinal
    "colon":  re.compile(r"^\s*\d{4}:"),         # 4010:Desc     Holden
    "mri":    re.compile(r"^\s*\d-\d{4}-\d"),     # 1-5000-0005   Crystal Lake
    "5digit": re.compile(r"^\d{5}-\d"),          # 41000-000     Eleven11 / Mesquite
}

# Six kinds a cell can be. The five TEXT kinds drive the format decision;
# `numeric` is informational — it shows where the value columns are.
KINDS       = ["pure_code", "embedded_code", "foreign_code", "indented_text", "plain_text", "numeric"]
TEXT_KINDS  = {"pure_code", "embedded_code", "foreign_code", "indented_text", "plain_text"}
NCOLS       = 6                                   # scan columns A..F
COL_LETTERS = ["a", "b", "c", "d", "e", "f"]


def cell_kind(v):
    """Categorize ONE cell value into exactly one kind (priority order), or None."""
    if isinstance(v, (int, float)):
        return "numeric"
    if not (isinstance(v, str) and v.strip()):
        return None
    raw, s = v, v.strip()
    if PURE_CODE.match(s):
        return "pure_code"
    if any(p.match(raw) for p in FOREIGN_CODES.values()):
        return "foreign_code"
    if EMBEDDED_CODE.match(raw) and re.search(r"[A-Za-z]", re.sub(EMBEDDED_STRIP, "", raw)):
        return "embedded_code"
    if raw.startswith("  ") and re.search(r"[A-Za-z]", s) and not s[0].isdigit():
        return "indented_text"
    if re.search(r"[A-Za-z]", s):
        return "plain_text"
    return None


def extract_format_signals(grid, scan_rows=60):
    """For every column A-F over the first `scan_rows`, count how many text rows
    have a cell of each kind, then normalize. Reads cell_grid.
    Returns (counts, fractions, rows_with_text)."""
    rowmap = grid_row_map(grid)
    counts = {k: [0] * NCOLS for k in KINDS}
    rows_with_text = 0
    for r in range(1, min(grid["max_row"], scan_rows) + 1):
        grow = rowmap.get(r)
        had_text = False
        for c in range(NCOLS):
            k = cell_kind(gvalue(grow, c + 1))
            if k:
                counts[k][c] += 1
                if k in TEXT_KINDS:
                    had_text = True
        if had_text:
            rows_with_text += 1

    denom = max(rows_with_text, 1)
    fractions = {k: [round(counts[k][c] / denom, 3) for c in range(NCOLS)] for k in KINDS}
    return counts, fractions, rows_with_text


DECISION_THRESHOLD = 0.15   # best known-format score must clear this, else 'unknown'


def detect_format(grid, scan_rows=60):
    """Return {format, confidence, reason, scores, counts, fractions, rows_with_text}.
    Only the TEXT code-kinds in column A drive the decision; `numeric` is not used."""
    counts, F, rows_with_text = extract_format_signals(grid, scan_rows)

    # Known formats are anchored in column A → read their column-A fraction.
    scores = {
        "code_in_a_desc_in_b": F["pure_code"][0],
        "embedded_code_in_a":  F["embedded_code"][0],
        "no_code":             F["indented_text"][0],
        "unknown":             max(F["foreign_code"]),      # foreign style, any column
    }

    # Structural gate: where do codes dominate? If not column A, the file spreads
    # codes across columns (hierarchical / TREE) — not one of our flat formats.
    code_per_col = [F["pure_code"][c] + F["embedded_code"][c] + F["foreign_code"][c]
                    for c in range(NCOLS)]
    if sum(code_per_col) > 0:
        dom = max(range(NCOLS), key=lambda c: code_per_col[c])
        if dom != 0:
            return {"format": "unknown", "confidence": round(scores["unknown"], 3),
                    "reason": f"codes dominate column {COL_LETTERS[dom].upper()}, not A (hierarchical)",
                    "scores": scores, "counts": counts, "fractions": F, "rows_with_text": rows_with_text}

    best = max(scores, key=scores.get)
    if best == "unknown" or scores[best] < DECISION_THRESHOLD:
        return {"format": "unknown", "confidence": round(scores["unknown"], 3),
                "reason": "no known format cleared the threshold / foreign codes dominate",
                "scores": scores, "counts": counts, "fractions": F, "rows_with_text": rows_with_text}

    return {"format": best, "confidence": scores[best],
            "reason": f"{best} strongest in column A",
            "scores": scores, "counts": counts, "fractions": F, "rows_with_text": rows_with_text}
