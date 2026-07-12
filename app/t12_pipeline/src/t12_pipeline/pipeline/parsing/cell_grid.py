"""Layer 1 — read the workbook once, losslessly, into `cell_grid`.

Ported verbatim from notebook Module 3 (+ the Setup cell's load/save helpers).
`cell_grid` is a plain, JSON-serializable list of row records and is the single
source of truth for every downstream parsing module.
"""
import json
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

MAX_SCAN_ROWS, MAX_SCAN_COLS = 5000, 50   # guard against a phantom max_row / max_col


def _color(cobj):
    """Safe RGB string from an openpyxl color object, or None."""
    if cobj is None:
        return None
    rgb = getattr(cobj, "rgb", None)
    return rgb if isinstance(rgb, str) else None


def extract_cell_grid(path):
    """Layer 1 — read the workbook ONCE, losslessly, into cell_grid.
    Reads values (data_only=True) and formulas (data_only=False)."""
    wb_v = openpyxl.load_workbook(path, data_only=True);  ws_v = wb_v.active
    wb_f = openpyxl.load_workbook(path, data_only=False); ws_f = wb_f.active
    max_row = min(ws_v.max_row, MAX_SCAN_ROWS)
    max_col = min(ws_v.max_column, MAX_SCAN_COLS)

    rows = []
    for r in range(1, max_row + 1):
        cells = {}
        for c in range(1, max_col + 1):
            cv = ws_v.cell(row=r, column=c)
            fv = ws_f.cell(row=r, column=c).value
            formula = fv if (isinstance(fv, str) and fv.startswith("=")) else None
            bt = cv.border.top.style    if (cv.border and cv.border.top)    else None
            bb = cv.border.bottom.style if (cv.border and cv.border.bottom) else None
            fill_color = _color(cv.fill.fgColor) if (cv.fill and cv.fill.patternType) else None
            # keep any cell with content or non-default formatting; drop truly-empty cells
            if not ((cv.value is not None) or formula or bt or bb or fill_color or cv.comment or cv.hyperlink):
                continue
            cells[c] = {
                "col": c, "letter": get_column_letter(c),
                "value": cv.value, "formula": formula,
                "data_type": cv.data_type, "number_format": cv.number_format,
                "bold": bool(cv.font.bold) if cv.font else False,
                "italic": bool(cv.font.italic) if cv.font else False,
                "underline": cv.font.underline if cv.font else None,
                "font_size": cv.font.size if cv.font else None,
                "font_color": _color(cv.font.color) if cv.font else None,
                "align_h": cv.alignment.horizontal if cv.alignment else None,
                "indent": (cv.alignment.indent if cv.alignment else 0) or 0,
                "fill_color": fill_color,
                "border_top": bt, "border_bottom": bb,
                "comment": cv.comment.text if cv.comment else None,
                "hyperlink": cv.hyperlink.target if cv.hyperlink else None,
            }
        if cells:
            rows.append({"row": r, "cells": cells})

    grid = {
        "sheet": ws_v.title, "max_row": max_row, "max_col": max_col,
        "merged_ranges": [str(m) for m in ws_v.merged_cells.ranges],
        "hidden_rows": [r for r, d in ws_v.row_dimensions.items() if d.hidden],
        "hidden_cols": [k for k, d in ws_v.column_dimensions.items() if d.hidden],
        "rows": rows,
    }
    wb_v.close(); wb_f.close()
    return grid


def run(state):
    """Step: extract_grid — reads file.path, writes cell_grid (the run-state form)."""
    return {**state, "cell_grid": extract_cell_grid(state["file"]["path"])}


# ── helpers every downstream module uses to read the grid ─────────────────────
def grid_row_map(grid):
    """{sheet_row_number: row_record} for O(1) lookup by row number."""
    return {row["row"]: row for row in grid["rows"]}


def gcell(grow, col):
    """Cell dict at 1-based column `col` in a row record, or None."""
    return grow["cells"].get(col) if grow else None


def gvalue(grow, col):
    """Value at 1-based column `col`, or None."""
    c = gcell(grow, col)
    return c["value"] if c else None


# ── JSON round-trip (from the notebook Setup cell) ────────────────────────────
def save_cell_grid(grid, path):
    """Serialize cell_grid to JSON (parent dirs created)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(grid, f, default=str)


def load_cell_grid(path):
    """Load cell_grid and restore integer column keys (JSON stringifies dict keys)."""
    with open(path) as f:
        grid = json.load(f)
    for row in grid["rows"]:
        row["cells"] = {int(k): v for k, v in row["cells"].items()}
    return grid
