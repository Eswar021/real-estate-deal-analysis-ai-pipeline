"""
Reads auto_mapped JSON files (Stage 1b output) and writes one Excel per property.

Columns: Row # | Statement Side | Row Description | Mapping | Status

Usage:
    python pipeline/utils/auto_mapped_to_excel.py
"""

import json
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.paths import AUTO_MAPPED_DIR, RESULTS_TO_EXCEL_DIR

HEADER_FONT  = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
DATA_FONT    = Font(name="Calibri", size=10)
MAPPED_FILL  = PatternFill("solid", fgColor="E2EFDA")   # light green
MISSING_FONT = Font(name="Calibri", size=10, color="C00000")  # red
META_FONT    = Font(name="Calibri", size=10, color="7F7F7F")  # grey for headers/subtotals
BORDER       = Border(
    left=Side(style="thin", color="D9D9D9"), right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),  bottom=Side(style="thin", color="D9D9D9"),
)
WRAP = Alignment(vertical="center", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center")


def export(json_path: Path):
    data = json.load(open(json_path))
    file_name = data.get("file", json_path.name)
    rows = data.get("rows", [])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Auto Mapped"

    # Header row
    for col, label in enumerate(["Row #", "Statement Side", "Row Description", "Mapping", "Status"], 1):
        c = ws.cell(row=1, column=col, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER
        c.border = BORDER
    ws.freeze_panes = "A2"

    for i, r in enumerate(rows, start=2):
        row_type   = r.get("type", "")
        side       = r.get("statement_side", "")
        desc       = r.get("description", "")
        mapping    = r.get("mapping")
        not_found  = r.get("not_found", False)

        if row_type == "data":
            status  = "NOT FOUND" if not_found else "Mapped"
        elif row_type in ("header", "subtotal"):
            status  = row_type.capitalize()
            mapping = ""
        else:
            status  = ""
            mapping = ""

        ws.cell(row=i, column=1, value=r.get("row", "")).alignment = CENTER
        ws.cell(row=i, column=2, value=side).alignment = CENTER
        ws.cell(row=i, column=3, value=desc).alignment = WRAP
        ws.cell(row=i, column=4, value=mapping or "").alignment = WRAP
        ws.cell(row=i, column=5, value=status).alignment = CENTER

        for col in range(1, 6):
            ws.cell(row=i, column=col).font   = DATA_FONT
            ws.cell(row=i, column=col).border = BORDER

        if row_type == "data":
            if not_found:
                ws.cell(row=i, column=4).font = MISSING_FONT
                ws.cell(row=i, column=5).font = MISSING_FONT
            else:
                for col in range(1, 6):
                    ws.cell(row=i, column=col).fill = MAPPED_FILL
        elif row_type in ("header", "subtotal"):
            ws.cell(row=i, column=5).font = META_FONT

    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 46
    ws.column_dimensions["D"].width = 32
    ws.column_dimensions["E"].width = 12

    safe = file_name.replace(".xlsx", "").replace(" ", "_")
    out  = RESULTS_TO_EXCEL_DIR / f"{safe}.xlsx"
    wb.save(out)
    print(f"  Saved: {out.name}")


if __name__ == "__main__":
    files = sorted(AUTO_MAPPED_DIR.glob("*.json"))
    if not files:
        print(f"No files found in {AUTO_MAPPED_DIR}")
    else:
        print(f"Exporting {len(files)} auto-mapped file(s)...\n")
        for f in files:
            export(f)
