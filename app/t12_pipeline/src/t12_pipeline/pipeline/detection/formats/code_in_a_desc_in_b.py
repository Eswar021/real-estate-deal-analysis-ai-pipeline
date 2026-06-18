"""
Format: code_in_a_desc_in_b

Col A holds a pure account code (e.g. 5120-01 or 5120-9999).
Col B holds the description (e.g. "    Gross Possible Rent").

Row classification rules (checked in order):
  - Code ends in 9999                                       → SUBTOTAL
  - Description matches "Total ..." / grand-total keyword   → SUBTOTAL
  - Code + description + no values in monthly cols          → HEADER   (structural marker)
  - Code + B has 4-space indent                             → DATA
  - Code + ALL CAPS description (any indent)                → HEADER   (e.g. Carmel "EXPENSES")
  - Code + anything else                                    → DATA
  - No code in A, B has text                                → SUBTOTAL  (computed row)
  - Text in A, B empty                                      → HEADER    (section name in A only)
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


def _has_any_cell(ws, row, start_col=3, end_col=16):
    """True if any monthly column has a value (literal zeros count, blanks don't)."""
    for col in range(start_col, end_col + 1):
        if ws.cell(row=row, column=col).value is not None:
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

        # Subtotals can use "Total ..." / grand-total keywords without a -9999 code.
        # Check this BEFORE the no-values rule so a "Total X" row with empty cells
        # is still classified as subtotal, not header.
        if _is_total_text(b_str):
            return "subtotal", b_str

        # Structural rule: code + description + no values in monthly columns =
        # section header. Catches Carmel rows 50/51/52 ("5000-0000 EXPENSES")
        # with zero indent + ALL CAPS + all blank monthly cells. Reliable
        # because a real data row always has at least one cell value.
        if not _has_any_cell(ws, row, start_col=3):
            return "header", b_str

        b_raw = str(b) if b else ""
        if b_raw.startswith("    "):
            return "data", b_str

        # ALL CAPS description = section header. Previously required a leading
        # space in col B; loosened because some files (Carmel) write section
        # headers flush-left. Subtotal cases were filtered above (-9999 codes
        # and "Total ..." text), so any ALL CAPS row reaching here is a
        # structural header. Audited zero regressions across supported files.
        if b_str.upper() == b_str and any(c.isalpha() for c in b_str):
            return "header", b_str

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
