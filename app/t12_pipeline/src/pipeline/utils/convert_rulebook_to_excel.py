"""
Converts the active mapping rulebook JSON to a simple one-sheet Excel.

Layout:
    Section header row → data rows per entry
    Col A: Row Description
    Col B+: Section-specific detail columns

Usage:
    python pipeline/utils/convert_rulebook_to_excel.py
"""

import json
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.paths import RULEBOOK_EXCEL_PATH
from config.rulebook_runtime import get_active_rulebook_name, get_active_rulebook_path

RULEBOOK_PATH = get_active_rulebook_path()

with open(RULEBOOK_PATH, "r", encoding="utf-8") as f:
    rulebook = json.load(f)

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Mapping Rulebook"

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
COL_FILL    = PatternFill("solid", fgColor="D6E4F0")
COL_FONT    = Font(name="Calibri", bold=True, size=10)
BODY_FONT   = Font(name="Calibri", size=10)
WRAP        = Alignment(vertical="center", wrap_text=True)

row = 1


def section_header(label):
    global row
    ws.cell(row=row, column=1, value=label).font = HEADER_FONT
    ws.cell(row=row, column=1).fill = HEADER_FILL
    ws.row_dimensions[row].height = 18
    row += 1


def col_headers(*labels):
    global row
    for col, label in enumerate(labels, start=1):
        c = ws.cell(row=row, column=col, value=label)
        c.font = COL_FONT
        c.fill = COL_FILL
    row += 1


def data_row(*values):
    global row
    for col, val in enumerate(values, start=1):
        c = ws.cell(row=row, column=col, value=val or "")
        c.font = BODY_FONT
        c.alignment = WRAP
    row += 1


# ── certain ───────────────────────────────────────────────────────────────────
section_header("CERTAIN  —  Client-reviewed direct mappings")
col_headers("Row Description", "Mapping", "Review Note")
for entry in rulebook.get("certain", {}).values():
    data_row(entry["row_description"], entry["mapping"], entry.get("review_note") or "")
row += 1  # blank spacer

# ── contextual ────────────────────────────────────────────────────────────────
section_header("CONTEXTUAL  —  Mapping depends on statement side or section")
col_headers("Row Description", "Rule Type", "Detail")
for entry in rulebook.get("contextual", {}).values():
    if entry["rule_type"] == "statement_side":
        cond = entry.get("conditions", {})
        detail = "  |  ".join(f"{side} → {mapping}" for side, mapping in sorted(cond.items()))
    elif entry["rule_type"] == "section_rule":
        parts = [f"default → {entry.get('default_mapping', '—')}"]
        for sr in entry.get("section_rules", []):
            parts.append(f"if section contains '{sr['section_contains']}' → {sr['mapping']}")
        detail = "  |  ".join(parts)
    else:
        detail = ""
    data_row(entry["row_description"], entry["rule_type"], detail)
row += 1

# ── unresolved ────────────────────────────────────────────────────────────────
section_header("UNRESOLVED  —  Could not be mapped to a single category")
col_headers("Row Description", "Historical Candidate Mappings", "Reason", "Review Note")
for entry in rulebook.get("unresolved", {}).values():
    candidates = ", ".join(entry.get("historical_candidate_mappings") or [])
    data_row(
        entry["row_description"],
        candidates,
        entry.get("reason_type") or "",
        entry.get("review_note") or "",
    )
row += 1

# ── no_conflict ───────────────────────────────────────────────────────────────
section_header("NO CONFLICT  —  Auto-mapped (consistent across all files)")
col_headers("Row Description", "Mapping")
for entry in rulebook.get("no_conflict", {}).values():
    data_row(entry["row_description"], entry["mapping"])

# ── column widths ─────────────────────────────────────────────────────────────
ws.column_dimensions["A"].width = 48
ws.column_dimensions["B"].width = 36
ws.column_dimensions["C"].width = 60
ws.column_dimensions["D"].width = 55

wb.save(RULEBOOK_EXCEL_PATH)
print(f"Saved → {RULEBOOK_EXCEL_PATH}")
print(f"Source : {get_active_rulebook_name()} → {RULEBOOK_PATH}")
