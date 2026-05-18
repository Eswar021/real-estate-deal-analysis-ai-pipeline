"""
Format: embedded_code_in_a

Col A contains everything: code + description merged (e.g. "5120 - Gross Possible Rent").
Col B is unused for classification.

Row classification rules:
  - Col A matches embedded code pattern   → DATA     (strip code, keep description)
  - Col A starts with "Total" or is a grand-total keyword → SUBTOTAL
  - Col A has indent > 4 spaces (no code) → DATA     (deeply indented line item)
  - Col A has text, none of the above     → HEADER
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
        return "data", desc

    if _is_total_text(a_str):
        return "subtotal", a_str

    # Deep-indented rows without a code are data items (e.g. "Customer Support Team Salaries").
    # Section headers always use shallower indentation (≤4 spaces) than data rows (6+ spaces).
    if indent > 4 and a_str:
        return "data", a_str

    if a_str:
        return "header", a_str

    return "empty", ""
