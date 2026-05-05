"""
results_to_excel.py — Step 3 of the pipeline

Reads the mapped_block_results.json (output of map_blocks)
and generates styled Excel files for review.

Pipeline:
  detect_blocks.py → block_detection_results.json
  map_blocks.py    → mapped_block_results.json
  results_to_excel.py → Excel files   (this script)
"""

import json
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

import sys
from pathlib import Path

# Add project root to sys.path so we can import config
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    MAPPED_BLOCK_RESULTS_PATH,
    RESULTS_TO_EXCEL_DIR
)

# ── Load mapped data ──
with open(MAPPED_BLOCK_RESULTS_PATH) as f:
    all_results = json.load(f)


def export_to_excel(index=0):
    entry = all_results[index]
    file_name = entry["file"]
    rows = entry["rows"]
    fmt = entry["format"]
    summary = entry["summary"]

    print(f"Processing: {file_name} (format: {fmt}, {len(rows)} rows)")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Block Detection"

    # ── Styles ──
    header_font = Font(name="Calibri", bold=True, size=12, color="FFFFFF")
    header_fill = PatternFill(start_color="4F6272", end_color="4F6272", fill_type="solid")

    data_font = Font(name="Calibri", size=10)
    unmapped_font = Font(name="Calibri", size=10, color="C00000")
    likely_font = Font(name="Calibri", size=10, color="0070C0") # Blue font for Likely Header/Subtotal

    mapped_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

    thin_border = Border(
        bottom=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9")
    )

    # ── Column headers ──
    headers = ["Row #", "Type", "Row Description (from T12)", "Auto Mapping"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # ── Write rows ──
    for i, r in enumerate(rows, start=2):
        row_num = r["row"]
        row_type = r["type"]
        description = r["description"]
        mapping = r.get("mapping", None)
        not_found = r.get("not_found", False)

        ws.cell(row=i, column=1, value=row_num)
        ws.cell(row=i, column=2, value=row_type.upper())
        ws.cell(row=i, column=3, value=description)

        if row_type == "header":
            ws.cell(row=i, column=4, value="Likely Header")
        elif row_type == "subtotal":
            ws.cell(row=i, column=4, value="Likely Subtotal")
        elif row_type == "data":
            ws.cell(row=i, column=4, value=mapping or "⚠ NOT FOUND")
        else:
            ws.cell(row=i, column=4, value="")

        # ── Apply row-level styling ──
        for col in range(1, 5):
            ws.cell(row=i, column=col).font = data_font
            ws.cell(row=i, column=col).border = thin_border

        if row_type == "header" or row_type == "subtotal":
            ws.cell(row=i, column=4).font = likely_font
        elif row_type == "data":
            if not_found:
                ws.cell(row=i, column=4).font = unmapped_font
            else:
                # Optionally style mapped rows with a light green background
                # for col in range(1, 5):
                #     ws.cell(row=i, column=col).fill = mapped_fill
                pass

    # ── Column widths ──
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 45
    ws.column_dimensions["D"].width = 30

    # ── Freeze top row ──
    ws.freeze_panes = "A2"

    # ── Save ──
    safe_name = file_name.replace(".xlsx", "").replace(" ", "_")
    output_path = RESULTS_TO_EXCEL_DIR / f"mapped_results_{safe_name}.xlsx"
    wb.save(output_path)
    print(f"Saved: {output_path}")

    # Quick stats (read directly from the mapped JSON summary)
    print(f"  Data rows: {summary['data_rows']}")
    print(f"  Mapped:    {summary['mapped']}")
    print(f"  Unmapped:  {summary['unmapped']}")


if __name__ == "__main__":
    # ── Run ──
    print(f"Available files ({len(all_results)} total):")
    for idx, r in enumerate(all_results):
        s = r["summary"]
        print(f"  [{idx}] {r['file']}  (mapped: {s['mapped']}, unmapped: {s['unmapped']})")
    print()

    for i in range(len(all_results)):
        export_to_excel(i)
