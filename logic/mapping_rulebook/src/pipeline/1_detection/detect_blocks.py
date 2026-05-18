import openpyxl
import re
import json
import os
import glob

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.paths import (
    INPUT_T12_DOCS_DIR,
    BLOCK_DETECTION_DIR
)

# ── Account code patterns ──
ACCT_CODE_PATTERN = re.compile(r'^\d{4}-\d{2,4}$')
EMBEDDED_CODE_PATTERN = re.compile(r'^\s*\d{4}(\s*-\s*\d*\s*-?\s*)')
SUBTOTAL_CODE_PATTERN = re.compile(r'^\d{4}-9999$')

# ── Known grand-total keywords (not starting with "Total") ──
GRAND_TOTAL_KEYWORDS = [
    "net operating income", "effective gross income", "net rental revenue",
    "net rental income", "net income", "net rent revenue", "net cash flow",
    "collectible rental revenue", "adjusted gross possible rental revenue",
    "total net rent", "total income", "total revenue", "total expenses",
    "total operating expenses", "total operating revenues",
    "taxable income", "income after debt service",
]

# ── Grand income total markers — the specific subtotal rows that signal the end
#    of the income section and the start of the expense section.
#    After one of these subtotals is seen, all subsequent data rows are expense.
#    These are a strict subset of GRAND_TOTAL_KEYWORDS: only rows that reliably
#    mark the income→expense boundary, not any mid-income sub-totals.
GRAND_INCOME_TOTAL_MARKERS = frozenset({
    "total income",            # Brownsburg, Pebble Brook 03-25
    "total revenue",           # Carmel Woods
    "effective gross income",  # Pebble Brook 09-25, Pointe Inverness, Willows
    "total operating revenues",# Echo Park
})

# Marks the end of operating expenses — everything after is capex/below-NOI.
# Only checked once income_phase_complete is True (guard against summary NOI
# rows at the top of some files, e.g. Pebble Brook 03-25 row 12).
GRAND_NOI_MARKERS = frozenset({
    "net operating income",  # covers "Net Operating Income", "(Loss)", "Total Net Operating Income"
})


# ═══════════════════════════════════════════════════════════════
#  FORMAT DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_format(ws):
    """
    Detect file format by sampling the first 60 rows.
    Returns: 'code_in_a_desc_in_b' | 'embedded_code_in_a' | 'no_code'
    """
    code_in_a_count = 0
    embedded_code_count = 0

    for row in range(1, min(ws.max_row + 1, 60)):
        a = ws.cell(row=row, column=1).value
        if a and isinstance(a, str):
            a_stripped = a.strip()
            if ACCT_CODE_PATTERN.match(a_stripped):
                code_in_a_count += 1
            elif EMBEDDED_CODE_PATTERN.match(a_stripped):
                embedded_code_count += 1

    if code_in_a_count >= 5:
        return "code_in_a_desc_in_b"
    elif embedded_code_count >= 3:
        return "embedded_code_in_a"
    else:
        return "no_code"


# ═══════════════════════════════════════════════════════════════
#  DATA START ROW DETECTION
# ═══════════════════════════════════════════════════════════════

def find_data_start_row(ws, fmt):
    """Find the first row of actual financial data (skip metadata)."""
    income_keywords = ["income", "revenue", "rent", "rental"]

    for row in range(1, min(ws.max_row + 1, 30)):
        a = ws.cell(row=row, column=1).value
        if not a or not isinstance(a, str):
            continue
        a_s = a.strip()

        # If we see an account code, data has started
        if ACCT_CODE_PATTERN.match(a_s) or EMBEDDED_CODE_PATTERN.match(a_s):
            return row

        # If we see an income/revenue keyword, this is likely the first header
        if any(kw in a_s.lower() for kw in income_keywords):
            # Verify next few rows have data
            for r2 in range(row + 1, min(row + 5, ws.max_row + 1)):
                a2 = ws.cell(row=r2, column=1).value
                if a2 and isinstance(a2, str):
                    if ACCT_CODE_PATTERN.match(a2.strip()) or EMBEDDED_CODE_PATTERN.match(a2.strip()):
                        return row
                    if a2.strip() and a2.startswith("  "):
                        return row
    return 1


# ═══════════════════════════════════════════════════════════════
#  ROW CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def _has_numeric_data(ws, row, start_col=2, end_col=16):
    """Check if a row has any non-zero numeric values in the data columns."""
    for col in range(start_col, end_col + 1):
        v = ws.cell(row=row, column=col).value
        if isinstance(v, (int, float)) and v != 0:
            return True
    return False


def _is_total_text(text):
    """Check if text indicates a subtotal/total row."""
    t = text.strip().lower()
    if t.startswith("total ") or t == "total":
        return True
    # Use word-boundary matching to avoid false positives like
    # "cable/internet income" matching keyword "net income".
    if any(re.search(r'\b' + re.escape(kw) + r'\b', t) for kw in GRAND_TOTAL_KEYWORDS):
        return True
    return False


def _extract_description_from_code(text):
    """Strip embedded account code from text like '5120 - Gross Possible Rent'."""
    return re.sub(r'^\s*\d{4}(\s*-\s*\d*\s*-?\s*)', '', text).strip()


def classify_row(ws, row, fmt):
    """
    Classify a single row. Returns:
      (row_type, description)
      row_type: 'data' | 'header' | 'subtotal' | 'empty'
    """
    a = ws.cell(row=row, column=1).value
    b = ws.cell(row=row, column=2).value

    a_str = str(a).strip() if a else ""
    b_str = str(b).strip() if b else ""
    a_raw = str(a) if a else ""

    # ── Empty row ──
    if not a_str and not b_str:
        return "empty", ""

    # ═══ FORMAT A: code in col A, description in col B ═══
    if fmt == "code_in_a_desc_in_b":
        has_code = ACCT_CODE_PATTERN.match(a_str)

        if has_code and b_str:
            # Subtotal code (ends in 9999)
            if SUBTOTAL_CODE_PATTERN.match(a_str):
                return "subtotal", b_str

            # Check B indentation: leading spaces = data, no leading spaces = header
            b_raw = str(b) if b else ""
            if b_raw.startswith("    "):
                if _is_total_text(b_str):
                    return "subtotal", b_str
                return "data", b_str
            elif b_raw.startswith(" ") and b_str.upper() == b_str:
                # Single-space + ALL CAPS = section header (Carmel Woods)
                if _is_total_text(b_str):
                    return "subtotal", b_str
                return "header", b_str
            # Has code + has description = data by default, unless text is a total
            if _is_total_text(b_str):
                return "subtotal", b_str
            return "data", b_str

        if has_code and not b_str:
            # Code only, no description — skip
            return "empty", ""

        # Col A has text (not a code), col B is empty → HEADER
        if a_str and not b_str and not has_code:
            return "header", a_str

        # Col A is empty, col B has text → SUBTOTAL
        if not a_str and b_str:
            if _is_total_text(b_str):
                return "subtotal", b_str
            # In Format A: empty A + text in B with numbers = computed subtotal
            if _has_numeric_data(ws, row, start_col=3):
                return "subtotal", b_str
            return "subtotal", b_str

        return "unknown", a_str or b_str

    # ═══ FORMAT B: embedded code in col A ═══
    elif fmt == "embedded_code_in_a":
        indent = len(a_raw) - len(a_raw.lstrip()) if a else 0

        # Check for embedded account code
        if EMBEDDED_CODE_PATTERN.match(a_raw):
            desc = _extract_description_from_code(a_raw)
            if not desc:
                desc = a_str
            return "data", desc

        # Subtotal: starts with "Total"
        if _is_total_text(a_str):
            return "subtotal", a_str

        # Deep-indented rows without a code are data items (e.g. "Customer Support Team Salaries").
        # Section headers always use shallower indentation (≤4 spaces) than data rows (6+ spaces).
        if indent > 4 and a_str:
            return "data", a_str

        # Header: text without code, not a total
        if a_str:
            return "header", a_str

        return "empty", ""

    # ═══ FORMAT C: no codes at all (Echo Park) ═══
    else:  # fmt == "no_code"
        indent = len(a_raw) - len(a_raw.lstrip()) if a else 0

        # Subtotal: starts with "Total"
        if _is_total_text(a_str):
            return "subtotal", a_str

        # Indented = DATA
        if indent >= 2:
            return "data", a_str

        # indent=0 + has numbers + no "Total" = computed grand total
        if indent == 0 and _has_numeric_data(ws, row):
            return "subtotal", a_str

        # indent=0 + no numbers + no "Total" = HEADER
        if indent == 0 and a_str:
            return "header", a_str

        return "empty", ""


# ═══════════════════════════════════════════════════════════════
#  MAIN CLASSIFICATION PIPELINE
# ═══════════════════════════════════════════════════════════════

def classify_file(file_path):
    """
    Classify every row in a T12 file.
    Returns a dict with file metadata and a flat list of classified rows.
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active

    fmt = detect_format(ws)
    start_row = find_data_start_row(ws, fmt)
    data_start_col = 3 if fmt == "code_in_a_desc_in_b" else 2

    column_headers = []
    header_row_idx = None
    if start_row > 1:
        # Search upwards for the best header row (most unique values = dates/months)
        best_headers = []
        best_score = -1
        
        for r in range(start_row - 1, 0, -1):
            vals = []
            for col in range(data_start_col, ws.max_column + 1):
                val = ws.cell(row=r, column=col).value
                vals.append(str(val).strip() if val is not None else "")
                
            non_empty = [v for v in vals if v]
            if not non_empty:
                continue
                
            # Score by uniqueness. 
            unique_non_empty = set(non_empty)
            score = len(unique_non_empty)
            
            if score > best_score and score >= 4:
                best_score = score
                best_headers = vals
                header_row_idx = r
                
            if score >= 10: # Found a row with distinct months, stop searching
                column_headers = vals
                header_row_idx = r
                break
        
        if not column_headers and best_headers:
            column_headers = best_headers

    if column_headers and header_row_idx:
        # Check row below
        row_below_vals = []
        for col in range(data_start_col, ws.max_column + 1):
            val = ws.cell(row=header_row_idx + 1, column=col).value
            row_below_vals.append(str(val).strip() if val is not None else "")
            
        # Check row above
        row_above_vals = []
        if header_row_idx > 1:
            for col in range(data_start_col, ws.max_column + 1):
                val = ws.cell(row=header_row_idx - 1, column=col).value
                row_above_vals.append(str(val).strip() if val is not None else "")
        else:
            row_above_vals = [""] * len(column_headers)

        # Merge information from row below and row above if header is empty
        for i, h in enumerate(column_headers):
            if not h:
                if i < len(row_below_vals) and "total" in row_below_vals[i].lower():
                    column_headers[i] = "Total"
                elif i < len(row_above_vals) and "total" in row_above_vals[i].lower():
                    column_headers[i] = "Total"
        
        # Find the actual end of the table
        first_non_empty = -1
        for i, h in enumerate(column_headers):
            if h:
                first_non_empty = i
                break
                
        last_valid_idx = -1
        if first_non_empty != -1:
            total_idx = -1
            for i, h in enumerate(column_headers):
                if h.lower() in ["total", "12-month total", "ytd total"]:
                    total_idx = i
                    break # find first total
            
            if total_idx != -1:
                last_valid_idx = total_idx
            else:
                curr = first_non_empty
                while curr < len(column_headers) and column_headers[curr]:
                    curr += 1
                last_valid_idx = curr - 1
        
        if last_valid_idx != -1:
            column_headers = column_headers[:last_valid_idx + 1]

    data_end_col = data_start_col + len(column_headers) - 1 if column_headers else ws.max_column

    print(f"File: {os.path.basename(file_path)}")
    print(f"  Format: {fmt}")
    print(f"  Data start row: {start_row}")

    classified_rows = []
    current_section = None
    current_path = []
    pending_headers = []
    previous_non_empty_type = None
    income_phase_complete = False  # flips once when grand income total subtotal is seen
    capex_phase_complete  = False  # flips once when NOI subtotal is seen (after income flip)

    for row in range(start_row, ws.max_row + 1):
        row_type, description = classify_row(ws, row, fmt)

        if row_type == "empty":
            continue

        # For subtotals: capture statement_side using the PRE-FLIP phase state,
        # then update the phase flags. This ensures the grand income total subtotal
        # (e.g. "Effective Gross Income") gets statement_side="revenue", not "expense".
        subtotal_side = None
        if row_type == "subtotal":
            if capex_phase_complete:
                subtotal_side = "capex"
            elif income_phase_complete:
                subtotal_side = "expense"
            else:
                subtotal_side = "revenue"

            desc_lower = description.strip().lower()
            if not income_phase_complete:
                if any(marker in desc_lower for marker in GRAND_INCOME_TOTAL_MARKERS):
                    income_phase_complete = True
            elif not capex_phase_complete:
                if any(marker in desc_lower for marker in GRAND_NOI_MARKERS):
                    capex_phase_complete = True

        if row_type == "header":
            if previous_non_empty_type == "header":
                pending_headers.append(description)
            else:
                pending_headers = [description]
            current_section = description
            active_path = list(pending_headers)
        else:
            if row_type == "data" and pending_headers:
                current_path = list(pending_headers)
                pending_headers = []

            active_path = list(current_path)
            if active_path:
                current_section = active_path[-1]

        classified_row = {
            "row": row,
            "type": row_type,
            "description": description,
            "section_context": current_section,
            "section_path": active_path,
        }

        if row_type == "data":
            if capex_phase_complete:
                classified_row["statement_side"] = "capex"
            elif income_phase_complete:
                classified_row["statement_side"] = "expense"
            else:
                classified_row["statement_side"] = "revenue"
        elif row_type == "subtotal":
            classified_row["statement_side"] = subtotal_side

        if row_type in ("data", "subtotal"):
            values = []
            for col in range(data_start_col, data_end_col + 1):
                val = ws.cell(row=row, column=col).value
                values.append(val if val is not None else 0)
            classified_row["values"] = values

        classified_rows.append(classified_row)
        previous_non_empty_type = row_type

    # Summary counts
    data_count = sum(1 for r in classified_rows if r["type"] == "data")
    header_count = sum(1 for r in classified_rows if r["type"] == "header")
    subtotal_count = sum(1 for r in classified_rows if r["type"] == "subtotal")
    print(f"  Classified: {data_count} data, {header_count} headers, {subtotal_count} subtotals")

    wb.close()

    return {
        "file": os.path.basename(file_path),
        "file_path": str(file_path),
        "format": fmt,
        "data_start_row": start_row,
        "column_headers": column_headers,
        "summary": {
            "data_rows": data_count,
            "headers": header_count,
            "subtotals": subtotal_count,
        },
        "rows": classified_rows,
    }


def print_classification(result):
    """Pretty-print the classified rows."""
    print(f"\n{'='*70}")
    print(f"File: {result['file']} | Format: {result['format']}")
    print(f"Data: {result['summary']['data_rows']} | "
          f"Headers: {result['summary']['headers']} | "
          f"Subtotals: {result['summary']['subtotals']}")
    print(f"{'='*70}")

    for r in result["rows"]:
        if r["type"] == "header":
            print(f"  📁 Row {r['row']:3d}  HEADER    │ {r['description']}")
        elif r["type"] == "subtotal":
            print(f"  Σ  Row {r['row']:3d}  SUBTOTAL  │ {r['description']}")
        elif r["type"] == "data":
            print(f"  📊 Row {r['row']:3d}  DATA      │ {r['description']:<45} [section: {r['section_context']}]")
        else:
            print(f"  ?  Row {r['row']:3d}  {r['type']:<9} │ {r['description']}")


if __name__ == "__main__":
    files = sorted([str(f) for f in INPUT_T12_DOCS_DIR.glob("*.xlsx")
                     if not f.name.startswith("~$")])
    print(f"Found {len(files)} files\n")

    for f in files:
        result = classify_file(f)
        print_classification(result)
        print()
        
        json_name = Path(f).stem + ".json"
        out_path = BLOCK_DETECTION_DIR / json_name
        with open(out_path, "w") as fp:
            json.dump(result, fp, indent=2)
        print(f"Saved results to {out_path}")
