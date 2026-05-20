"""
compute_noi.py — Stage 1c

Computes NOI two ways for each file and extracts the vendor's reported NOI.

Step 1 — Extract actual NOI:
  Reads the annotated block JSON and pulls the values from the is_noi subtotal row.
  This is the vendor's reported NOI — no computation, just read the row.

Step 2 — Compute NOI (row method):
  Sums all DATA rows by statement_side (revenue → add, expense → subtract, capex → skip).
  Does NOT require a mapping — statement_side from detect_blocks is sufficient.

Step 3 — Extract subtotal anchors:
  Pulls is_total_revenue subtotal row values per month.
  Used by compare_noi to check revenue and implied-expense accuracy separately,
  isolating WHERE any discrepancy comes from (revenue extraction vs expense extraction).

Reads:
    manifest["l1"]["paths"]["annotated_blocks_dir"]

Writes:
    manifest["l1"]["paths"]["actual_noi_dir"]
    manifest["l1"]["paths"]["computed_noi_dir"]

Does not call an LLM.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

# ═══════════════════════════════════════════════════════════════
#  STEP 1 — EXTRACT ACTUAL NOI
# ═══════════════════════════════════════════════════════════════

def find_actual_noi_row(rows):
    """
    Find the primary NOI subtotal row — the one with real numeric values.
    Some files have a summary NOI row at the top with no values; we want
    the bottom one that carries actual monthly data.
    """
    candidates = [r for r in rows if r.get("is_noi") and r.get("type") == "subtotal"]
    for row in reversed(candidates):
        if any(isinstance(v, (int, float)) for v in row.get("values", [])):
            return row
    return candidates[0] if candidates else None


def extract_actual_noi(file_data):
    rows = file_data.get("rows", [])
    column_headers = file_data.get("column_headers", [])

    noi_row = find_actual_noi_row(rows)
    if noi_row is None:
        return {
            "file": file_data["file"],
            "format": file_data.get("format"),
            "column_headers": column_headers,
            "noi_found": False,
            "noi_row": None,
            "error": "No NOI subtotal row found — check file structure",
        }

    values = noi_row.get("values", [])
    numeric_values = [v for v in values if isinstance(v, (int, float))]
    return {
        "file": file_data["file"],
        "format": file_data.get("format"),
        "column_headers": column_headers,
        "noi_found": True,
        "noi_row": {
            "row_number": noi_row["row"],
            "description": noi_row["description"],
            "values": values,
            "total": numeric_values[-1] if numeric_values else None,
        },
    }


# ═══════════════════════════════════════════════════════════════
#  STEP 2+3 — COMPUTE NOI FROM DATA ROWS + SUBTOTAL ANCHORS
# ═══════════════════════════════════════════════════════════════

def compute_noi(file_data):
    """
    Compute NOI by summing all DATA rows using statement_side from detect_blocks.
    No mapping required — statement_side alone determines revenue vs expense.
    Capex rows are always skipped (they are below-NOI-line items).

    Also extracts is_total_revenue subtotal values for the revenue accuracy check
    in compare_noi (row-method revenue vs vendor's EGI subtotal).
    """
    column_headers = file_data.get("column_headers", [])
    n_cols = len(column_headers)

    revenue_by_month  = [0.0] * n_cols
    expenses_by_month = [0.0] * n_cols
    skipped_rows = []
    unmapped_rows = []  # informational only — no longer excludes rows from NOI

    for row in file_data.get("rows", []):
        if row["type"] != "data":
            continue

        values = row.get("values", [])
        if not values:
            continue

        statement_side = row.get("statement_side")

        if statement_side == "capex":
            skipped_rows.append({"row": row["row"], "description": row["description"]})
            continue

        if statement_side not in ("revenue", "expense"):
            unmapped_rows.append({"row": row["row"], "description": row["description"],
                                  "statement_side": statement_side})
            continue

        for i in range(min(n_cols, len(values))):
            val = values[i]
            if not isinstance(val, (int, float)):
                continue
            if statement_side == "revenue":
                revenue_by_month[i] += val
            else:
                expenses_by_month[i] += val

    computed_noi_by_month = [
        round(revenue_by_month[i] - expenses_by_month[i], 2)
        for i in range(n_cols)
    ]

    # Subtotal anchor: is_total_revenue row values (vendor's EGI per month)
    total_rev_row = next(
        (r for r in file_data.get("rows", [])
         if r.get("is_total_revenue") and r.get("type") == "subtotal"),
        None,
    )
    revenue_subtotal_by_month = (
        [v if isinstance(v, (int, float)) else None for v in total_rev_row.get("values", [])]
        if total_rev_row else [None] * n_cols
    )

    return {
        "file": file_data["file"],
        "format": file_data.get("format"),
        "column_headers": column_headers,
        "revenue_by_month":           [round(v, 2) for v in revenue_by_month],
        "expenses_by_month":          [round(v, 2) for v in expenses_by_month],
        "computed_noi_by_month":      computed_noi_by_month,
        "revenue_subtotal_by_month":  revenue_subtotal_by_month,
        "total_revenue":              round(revenue_by_month[-1], 2) if column_headers else 0,
        "total_expenses":             round(expenses_by_month[-1], 2) if column_headers else 0,
        "computed_total_noi":         round(computed_noi_by_month[-1], 2) if column_headers else 0,
        "total_revenue_subtotal":     revenue_subtotal_by_month[-1] if revenue_subtotal_by_month else None,
        "skipped_rows":               skipped_rows,
        "unmapped_rows":              unmapped_rows,
    }


if __name__ == "__main__":
    from config.paths import MANIFEST_PATH
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"No manifest at {MANIFEST_PATH}. Run Stage 0 first.")

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    annotated_blocks_dir = Path(manifest["l1"]["paths"]["annotated_blocks_dir"])
    actual_noi_dir       = Path(manifest["l1"]["paths"]["actual_noi_dir"])
    computed_noi_dir     = Path(manifest["l1"]["paths"]["computed_noi_dir"])

    json_files = sorted(annotated_blocks_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No files in {annotated_blocks_dir}")

    for jfile in json_files:
        with open(jfile) as f:
            file_data = json.load(f)

        actual = extract_actual_noi(file_data)
        with open(actual_noi_dir / jfile.name, "w") as f:
            json.dump(actual, f, indent=2)

        computed = compute_noi(file_data)
        with open(computed_noi_dir / jfile.name, "w") as f:
            json.dump(computed, f, indent=2)

        print(f"  {computed['file']}  NOI: ${computed['computed_total_noi']:,.2f}")
