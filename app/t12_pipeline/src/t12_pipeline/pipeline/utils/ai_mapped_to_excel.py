"""
Reads ai_mapped JSON files (Stage 1c output) and writes one Excel per property.

Columns: Row # | Statement Side | Row Description | Final Mapping | Source | AI Confidence | AI Reasoning

Usage:
    python pipeline/utils/ai_mapped_to_excel.py
"""

import json
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from t12_pipeline.config.paths import AI_MAPPED_DIR, AI_MAPPED_TO_EXCEL_DIR

HEADER_FONT  = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
DATA_FONT    = Font(name="Calibri", size=10)
RULEBOOK_FILL = PatternFill("solid", fgColor="E2EFDA")   # green — rulebook mapped
AI_FILL       = PatternFill("solid", fgColor="FFF2CC")   # yellow — AI mapped
MISSING_FONT  = Font(name="Calibri", size=10, color="C00000")
META_FONT     = Font(name="Calibri", size=10, color="7F7F7F")
BORDER = Border(
    left=Side(style="thin", color="D9D9D9"), right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),  bottom=Side(style="thin", color="D9D9D9"),
)
WRAP   = Alignment(vertical="top", wrap_text=True)
CENTER = Alignment(horizontal="center", vertical="center")


def export(json_path: Path):
    data = json.load(open(json_path))
    file_name = data.get("file", json_path.name)
    rows = data.get("rows", [])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AI Mapped"

    headers = ["Row #", "Statement Side", "Row Description", "Final Mapping", "Source", "AI Confidence", "AI Reasoning"]
    for col, label in enumerate(headers, 1):
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
        ai_mapping = r.get("ai_suggested_mapping")
        ai_conf    = r.get("ai_confidence", "")
        ai_reason  = r.get("ai_reasoning", "")

        if row_type == "data":
            if not not_found:
                final   = mapping or ""
                source  = "Rulebook"
                ai_conf = ai_reason = ""
            elif ai_mapping:
                final  = ai_mapping
                source = "AI"
            else:
                final  = ""
                source = "NOT FOUND"
                ai_conf = ai_reason = ""
        else:
            final = source = ai_conf = ai_reason = ""

        ws.cell(row=i, column=1, value=r.get("row", "")).alignment = CENTER
        ws.cell(row=i, column=2, value=side).alignment = CENTER
        ws.cell(row=i, column=3, value=desc).alignment = WRAP
        ws.cell(row=i, column=4, value=final).alignment = WRAP
        ws.cell(row=i, column=5, value=source).alignment = CENTER
        ws.cell(row=i, column=6, value=ai_conf).alignment = CENTER
        ws.cell(row=i, column=7, value=ai_reason).alignment = WRAP

        for col in range(1, 8):
            ws.cell(row=i, column=col).font   = DATA_FONT
            ws.cell(row=i, column=col).border = BORDER

        if row_type == "data":
            if source == "Rulebook":
                for col in range(1, 8):
                    ws.cell(row=i, column=col).fill = RULEBOOK_FILL
            elif source == "AI":
                for col in range(1, 8):
                    ws.cell(row=i, column=col).fill = AI_FILL
            else:
                ws.cell(row=i, column=4).font = MISSING_FONT
                ws.cell(row=i, column=5).font = MISSING_FONT
        elif row_type in ("header", "subtotal"):
            ws.cell(row=i, column=5).font = META_FONT

    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 46
    ws.column_dimensions["D"].width = 32
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 15
    ws.column_dimensions["G"].width = 62

    safe = file_name.replace(".xlsx", "").replace(" ", "_")
    out  = AI_MAPPED_TO_EXCEL_DIR / f"{safe}.xlsx"
    wb.save(out)
    print(f"  Saved: {out.name}")


if __name__ == "__main__":
    files = sorted(AI_MAPPED_DIR.glob("*.json"))
    if not files:
        print(f"No files found in {AI_MAPPED_DIR}")
    else:
        print(f"Exporting {len(files)} AI-mapped file(s)...\n")
        for f in files:
            export(f)
