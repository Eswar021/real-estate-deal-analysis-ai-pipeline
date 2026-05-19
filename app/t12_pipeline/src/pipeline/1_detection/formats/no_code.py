"""
Format: no_code

Col A contains everything (description only, no account codes).
Classification is purely indentation-based.

Row classification rules:
  - Text matches a grand-total keyword or starts with "Total" → SUBTOTAL
  - indent >= 2                                               → DATA
  - indent == 0 AND has numeric values in data columns        → SUBTOTAL  (computed grand total)
  - indent == 0, no numbers                                   → HEADER
"""

import re

GRAND_TOTAL_KEYWORDS = [
    "net operating income", "effective gross income", "net rental revenue",
    "net rental income", "net income", "net rent revenue", "net cash flow",
    "collectible rental revenue", "adjusted gross possible rental revenue",
    "total net rent", "total income", "total revenue", "total expenses",
    "total operating expenses", "total operating revenues",
    "taxable income", "income after debt service",
]


def _has_numeric_data(ws, row, start_col=2, end_col=16):
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
    a_raw = str(a) if a else ""
    b_str = str(b).strip() if b else ""

    if not a_str and not b_str:
        return "empty", ""

    indent = len(a_raw) - len(a_raw.lstrip()) if a else 0

    if _is_total_text(a_str):
        return "subtotal", a_str

    if indent >= 2:
        return "data", a_str

    # indent=0 + has numbers + no "Total" = computed grand total
    if indent == 0 and _has_numeric_data(ws, row):
        return "subtotal", a_str

    if indent == 0 and a_str:
        return "header", a_str

    return "empty", ""
