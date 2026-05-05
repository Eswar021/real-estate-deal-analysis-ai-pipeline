"""
ai_results_to_excel.py — Step 4 (or post-AI) of the pipeline

Reads the AI mapped JSON files from AI_MAPPED_DIR
and generates styled Excel files for human review,
including the AI suggestions.
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
    AI_MAPPED_DIR,
    AI_MAPPED_TO_EXCEL_DIR
)

def export_ai_results_to_excel(json_path: Path):
    with open(json_path, "r") as f:
        data = json.load(f)

    file_name = data.get("file", json_path.name)
    rows = data.get("rows", [])
    
    print(f"Processing AI results: {file_name} ({len(rows)} rows)")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AI Mapping Review"

    # ── Styles ──
    header_font = Font(name="Calibri", bold=True, size=12, color="FFFFFF")
    header_fill = PatternFill(start_color="4F6272", end_color="4F6272", fill_type="solid")

    data_font = Font(name="Calibri", size=10)
    unmapped_font = Font(name="Calibri", size=10, color="C00000")
    likely_font = Font(name="Calibri", size=10, color="0070C0") # Blue font for Likely Header/Subtotal
    ai_suggested_font = Font(name="Calibri", size=10, bold=True, color="E36C09") # Orange for AI suggestions

    thin_border = Border(
        bottom=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9")
    )

    # ── Column headers ──
    headers = [
        "Row #", 
        "Type", 
        "Row Description (from T12)", 
        "Auto Mapping", 
        "AI Suggested Mapping", 
        "AI Confidence", 
        "AI Reasoning"
    ]
    
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # ── Write rows ──
    for i, r in enumerate(rows, start=2):
        row_num = r.get("row", "")
        row_type = r.get("type", "")
        description = r.get("description", "")
        mapping = r.get("mapping", None)
        not_found = r.get("not_found", False)
        
        ai_suggested = r.get("ai_suggested_mapping", "")
        ai_conf = r.get("ai_confidence", "")
        ai_reason = r.get("ai_reasoning", "")

        ws.cell(row=i, column=1, value=row_num)
        ws.cell(row=i, column=2, value=str(row_type).upper())
        ws.cell(row=i, column=3, value=description)

        if row_type == "header":
            ws.cell(row=i, column=4, value="Likely Header")
        elif row_type == "subtotal":
            ws.cell(row=i, column=4, value="Likely Subtotal")
        elif row_type == "data":
            ws.cell(row=i, column=4, value=mapping or "⚠ NOT FOUND")
        else:
            ws.cell(row=i, column=4, value="")

        # Write AI columns
        ws.cell(row=i, column=5, value=ai_suggested if ai_suggested else "")
        ws.cell(row=i, column=6, value=ai_conf if ai_conf else "")
        ws.cell(row=i, column=7, value=ai_reason if ai_reason else "")

        # ── Apply row-level styling ──
        for col in range(1, len(headers) + 1):
            ws.cell(row=i, column=col).font = data_font
            ws.cell(row=i, column=col).border = thin_border

        if row_type == "header" or row_type == "subtotal":
            ws.cell(row=i, column=4).font = likely_font
        elif row_type == "data":
            if not_found or not mapping:
                ws.cell(row=i, column=4).font = unmapped_font
                if ai_suggested:
                    ws.cell(row=i, column=5).font = ai_suggested_font

    # ── Column widths ──
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 45
    ws.column_dimensions["D"].width = 30
    ws.column_dimensions["E"].width = 35  # AI Suggested
    ws.column_dimensions["F"].width = 15  # AI Confidence
    ws.column_dimensions["G"].width = 60  # AI Reasoning
    
    # ── Wrap text for reasoning ──
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=7, max_col=7):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # ── Freeze top row ──
    ws.freeze_panes = "A2"

    # ── Save ──
    safe_name = file_name.replace(".xlsx", "").replace(" ", "_")
    output_path = AI_MAPPED_TO_EXCEL_DIR / f"ai_mapped_results_{safe_name}.xlsx"
    wb.save(output_path)
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    json_files = sorted(list(AI_MAPPED_DIR.glob("*.json")))
    if not json_files:
        print(f"No JSON files found in {AI_MAPPED_DIR}")
    else:
        print(f"Found {len(json_files)} file(s) in {AI_MAPPED_DIR}.\n")
        for j_file in json_files:
            export_ai_results_to_excel(j_file)
