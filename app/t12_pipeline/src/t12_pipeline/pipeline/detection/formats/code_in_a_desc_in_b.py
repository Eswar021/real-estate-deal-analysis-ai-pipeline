"""
Format: code_in_a_desc_in_b

Col A holds a pure account code (e.g. 5120-01 or 5120-9999).
Col B holds the description (e.g. "    Gross Possible Rent").

Row classification rules:
  - Code ends in 9999            → SUBTOTAL  (section total code)
  - Code + B has 4-space indent  → DATA      (indented = line item)
  - Code + B has 1-space + CAPS  → HEADER    (Carmel Woods section header style)
  - No code in A, B has text     → SUBTOTAL  (computed row, no account code)
  - Text in A, B empty           → HEADER    (section name in A only)
"""

import re

ACCT_CODE_PATTERN    = re.compile(r'^\d{4}-\d{2,4}$')
SUBTOTAL_CODE_PATTERN = re.compile(r'^\d{4}-9999$')

GRAND_TOTAL_KEYWORDS = [
    "net operating income", "effective gross income", "net rental revenue",
    "net rental income", "net income", "net rent revenue", "net cash flow",
    "collectible rental revenue", "adjusted gross possible rental revenue",
    "total net rent", "total income", "total revenue", "total expenses",
    "total operating expenses", "total operating revenues",
    "taxable income", "income after debt service",
]


def _has_numeric_data(ws, row, start_col=3, end_col=16):
    for col in range(start_col, end_col + 1):
        v = ws.cell(row=row, column=col).value
        if isinstance(v, (int, float)) and v != 0:
            return True
    return False


def _is_total_text(text):
    t = text.strip().lower()
    if t.startswith("total ") or t == "total":
        return True
    if any(re.search(r'\b' + re.escape(kw) + r'\b', t) for kw in GRAND_TOTAL_KEYWORDS):
        return True
    return False


def classify_row(ws, row):
    a = ws.cell(row=row, column=1).value
    b = ws.cell(row=row, column=2).value

    a_str = str(a).strip() if a else ""
    b_str = str(b).strip() if b else ""

    if not a_str and not b_str:
        return "empty", ""

    has_code = ACCT_CODE_PATTERN.match(a_str)

    if has_code and b_str:
        if SUBTOTAL_CODE_PATTERN.match(a_str):
            return "subtotal", b_str

        b_raw = str(b) if b else ""
        if b_raw.startswith("    "):
            if _is_total_text(b_str):
                return "subtotal", b_str
            return "data", b_str
        elif b_raw.startswith(" ") and b_str.upper() == b_str:
            # Single-space + ALL CAPS = section header (Carmel Woods style)
            if _is_total_text(b_str):
                return "subtotal", b_str
            return "header", b_str
        if _is_total_text(b_str):
            return "subtotal", b_str
        return "data", b_str

    if has_code and not b_str:
        return "empty", ""

    if a_str and not b_str and not has_code:
        return "header", a_str

    if not a_str and b_str:
        if _is_total_text(b_str):
            return "subtotal", b_str
        if _has_numeric_data(ws, row, start_col=3):
            return "subtotal", b_str
        return "subtotal", b_str

    return "unknown", a_str or b_str
