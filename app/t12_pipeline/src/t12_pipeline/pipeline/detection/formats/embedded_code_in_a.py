"""
Format: embedded_code_in_a

Col A contains everything: code + description merged (e.g. "5120 - Gross Possible Rent").
Col B is unused for classification.

Row classification rules (checked in order):
  - Col A matches embedded code + has values     → DATA      (real line item)
  - Col A matches embedded code + no values      → HEADER    (structural marker, rare)
  - Col A starts with "Total" / grand-total kw   → SUBTOTAL
  - Col A indent > 4 spaces + has values         → DATA      (deeply indented item)
  - Col A indent > 4 spaces + no values          → HEADER    (rare structural marker)
  - Col A has any text                           → HEADER
"""

import re

EMBEDDED_CODE_PATTERN = re.compile(r'^\s*\d{4}(\s*-\s*\d*\s*-?\s*)')

GRAND_TOTAL_KEYWORDS = [
    "net operating income", "effective gross income", "net rental revenue",
    "net rental income", "net income", "net rent revenue", "net cash flow",
    "collectible rental revenue", "adjusted gross possible rental revenue",
    "total net rent", "total income", "total revenue", "total expenses",
    "total operating expenses", "total operating revenues",
    "taxable income", "income after debt service",
]


def _is_total_text(text):
    t = text.strip().lower()
    if t.startswith("total ") or t == "total":
        return True
    if any(re.search(r'\b' + re.escape(kw) + r'\b', t) for kw in GRAND_TOTAL_KEYWORDS):
        return True
    return False


def _extract_description_from_code(text):
    return re.sub(r'^\s*\d{4}(\s*-\s*\d*\s*-?\s*)', '', text).strip()


def _has_any_cell(ws, row, start_col=2, end_col=16):
    """True if any monthly column has a value (literal zeros count, blanks don't)."""
    for col in range(start_col, end_col + 1):
        if ws.cell(row=row, column=col).value is not None:
            return True
    return False


def classify_row(ws, row):
    a = ws.cell(row=row, column=1).value

    a_str = str(a).strip() if a else ""
    a_raw = str(a) if a else ""

    if not a_str:
        return "empty", ""

    indent = len(a_raw) - len(a_raw.lstrip())

    if EMBEDDED_CODE_PATTERN.match(a_raw):
        desc = _extract_description_from_code(a_raw)
        if not desc:
            desc = a_str
        # Structural rule: embedded code + no values = section header, not data.
        # A real line item always has at least one cell value (literal zeros count).
        if not _has_any_cell(ws, row, start_col=2):
            return "header", desc
        return "data", desc

    if _is_total_text(a_str):
        return "subtotal", a_str

    # Deep-indented rows without a code are data items (e.g. "Customer Support Team Salaries").
    # Section headers always use shallower indentation (≤4 spaces) than data rows (6+ spaces).
    if indent > 4 and a_str:
        # Same structural rule: deep indent + no values = header (rare).
        if not _has_any_cell(ws, row, start_col=2):
            return "header", a_str
        return "data", a_str

    if a_str:
        return "header", a_str

    return "empty", ""
