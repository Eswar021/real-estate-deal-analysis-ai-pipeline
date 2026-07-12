"""Stage 0 — pre-flight screen (dict in, dict out).

Before any parsing or AI call, decide whether the workbook is a real T12 income statement
worth processing, or something to reject: a rent roll, a reviewed Model-T12 target file, or
a spreadsheet with no income-statement structure at all. Runs on the cell_grid; no AI.
"""
import re

from .anchor_lock import ANCHOR_KEYWORDS

# "rent roll" / "rentroll" anywhere, or "rr" as a delimited token (RR is the common abbrev.)
_RENT_ROLL_RE = re.compile(r"rent[\s_-]?roll|rentroll|(?:^|[\s_-])rr(?=[\s_.-]|$)", re.I)
_MODEL_RE     = re.compile(r"model[\s_-]*t-?12", re.I)


def _texts(cell_grid, max_col=6):
    """All non-empty text from the leftmost columns (descriptions live there in every T12
    format), flattened and lowercased for keyword matching."""
    out = []
    for grow in cell_grid["rows"]:
        for c in range(1, max_col + 1):
            cell = grow["cells"].get(c)
            if cell and isinstance(cell["value"], str):
                s = cell["value"].strip().lower()
                if s:
                    out.append(s)
    return out


def _has(texts, markers, exclusions=()):
    return any(any(m in t for m in markers) and not any(x in t for x in exclusions)
               for t in texts)


def screen_name(file_name="", sheet_name=""):
    """Name-only screen (no workbook read) — rejects rent rolls and Model-T12 target files.
    Returns a rejection {ok:False, kind, reason} or None if the name is clean."""
    name = f"{file_name} {sheet_name}"
    if _RENT_ROLL_RE.search(name):
        return {"ok": False, "kind": "rent_roll",
                "reason": "This looks like a rent roll, not a T12 income statement. "
                          "Please upload the property's trailing-12 income statement."}
    if _MODEL_RE.search(name):
        return {"ok": False, "kind": "model",
                "reason": "This is a reviewed Model T12 (a mapping target file), not a raw "
                          "T12 input. Please upload the vendor's original T12."}
    return None


def screen_structure(cell_grid):
    """Structural screen — a T12 always carries operating-expense subtotals; a rent roll
    never does. Returns {ok, kind, reason}."""
    texts = _texts(cell_grid)
    exp = ANCHOR_KEYWORDS["expense"]
    has_expense = (_has(texts, exp["grand_markers"], exp.get("exclusions", []))
                   or _has(texts, exp.get("intermediate_markers", []), exp.get("exclusions", [])))
    if not has_expense:
        return {"ok": False, "kind": "not_t12",
                "reason": "No income-statement structure found (no operating-expense total "
                          "row) — this doesn't look like a T12."}
    return {"ok": True, "kind": "t12", "reason": "T12 income statement."}


def preflight_check(cell_grid, file_name="", sheet_name=""):
    """Full screen (name + structure) for the CLI / one-shot callers. Returns
    {ok, kind, reason}; kind ∈ {t12, rent_roll, model, not_t12}."""
    return screen_name(file_name, sheet_name or cell_grid.get("sheet", "")) or screen_structure(cell_grid)
