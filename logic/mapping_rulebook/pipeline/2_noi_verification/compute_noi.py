"""
compute_noi.py — NOI Verification (Steps 1 + 2 combined)

Step 1 — Extract actual NOI:
  Reads ai_mapped JSON files and extracts the actual NOI subtotal row values
  reported by the vendor. No computation — just finds the NOI row and pulls
  the numbers as-is.

Step 2 — Compute NOI:
  Reads the same ai_mapped JSON files and computes NOI from the mapped DATA rows.
  For each DATA row, determines the final mapping and looks up its bucket
  (REVENUE / EXPENSE / SKIP) from category_classification.json.

  Final mapping logic (mirrors the Excel):
    final_mapping = auto_mapping  if row was found in rulebook
                    ai_suggested  if not found in rulebook but AI suggested one
                    None          if neither (row is unclassified)

Both steps run sequentially when this script is executed. Outputs go to separate
folders so compare_noi.py can read them independently.

Pipeline position:
  find_mapping (AI) → ai_mapped/
  compute_noi.py    ← this script  →  noi_verification/actual_noi/
                                       noi_verification/computed_noi/
  compare_noi.py    → noi_verification/comparison/

Input:  output_docs/<date>/1_mapping/ai_mapped/*.json
        db/category_classification.json
Output: output_docs/<date>/2_noi_verification/actual_noi/<filename>.json
        output_docs/<date>/2_noi_verification/computed_noi/<filename>.json
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    AI_MAPPED_DIR,
    ACTUAL_NOI_DIR,
    COMPUTED_NOI_DIR,
    CATEGORY_CLASSIFICATION_PATH,
)


# ═══════════════════════════════════════════════════════════════
#  STEP 1 — EXTRACT ACTUAL NOI
# ═══════════════════════════════════════════════════════════════

NOI_KEYWORDS = [
    "net operating income",
    "net operating income (loss)",
]


def find_noi_row(rows):
    """
    Find the primary NOI subtotal row — the one with actual numeric values.
    Some files have a duplicate NOI row at the top (summary header) with no values;
    we want the bottom one that has real monthly data.
    """
    candidates = [
        row for row in rows
        if row["type"] == "subtotal"
        and any(kw in row["description"].strip().lower() for kw in NOI_KEYWORDS)
    ]
    # Prefer the candidate that has at least one numeric value
    for row in reversed(candidates):
        values = row.get("values", [])
        if any(isinstance(v, (int, float)) for v in values):
            return row
    return candidates[0] if candidates else None


def extract_actual_noi(file_data):
    """
    Extract actual NOI values from a single ai_mapped file dict.
    Returns a result dict with noi_found flag and noi_row values.
    """
    rows = file_data.get("rows", [])
    column_headers = file_data.get("column_headers", [])

    noi_row = find_noi_row(rows)

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
#  STEP 2 — COMPUTE NOI FROM MAPPED ROWS
# ═══════════════════════════════════════════════════════════════

def load_classification():
    with open(CATEGORY_CLASSIFICATION_PATH) as f:
        return json.load(f)


def get_final_mapping(row):
    """Determine the best available mapping for a DATA row."""
    if not row.get("not_found"):
        return row.get("mapping")
    return row.get("ai_suggested_mapping")


def compute_noi(file_data, classification):
    """
    Compute NOI from mapped DATA rows in a single file.
    Returns a result dict with month-by-month revenue, expenses, and computed NOI.
    """
    column_headers = file_data.get("column_headers", [])
    n_cols = len(column_headers)

    revenue_by_month  = [0.0] * n_cols
    expenses_by_month = [0.0] * n_cols

    skipped_rows      = []
    unclassified_rows = []

    for row in file_data.get("rows", []):
        if row["type"] != "data":
            continue

        values = row.get("values", [])
        if not values:
            continue

        final_mapping = get_final_mapping(row)

        if final_mapping is None:
            unclassified_rows.append({
                "row": row["row"],
                "description": row["description"],
                "section_context": row.get("section_context"),
                "final_mapping": None,
            })
            continue

        bucket = classification.get(final_mapping, "UNCLASSIFIED")

        if bucket == "SKIP":
            skipped_rows.append({
                "row": row["row"],
                "description": row["description"],
                "category": final_mapping,
            })
            continue

        if bucket == "UNCLASSIFIED":
            unclassified_rows.append({
                "row": row["row"],
                "description": row["description"],
                "final_mapping": final_mapping,
                "note": "Category exists but not in classification config",
            })
            continue

        for i in range(min(n_cols, len(values))):
            val = values[i]
            if not isinstance(val, (int, float)):
                continue
            if bucket == "REVENUE":
                revenue_by_month[i] += val
            elif bucket == "EXPENSE":
                expenses_by_month[i] += val

    computed_noi_by_month = [
        round(revenue_by_month[i] - expenses_by_month[i], 2)
        for i in range(n_cols)
    ]

    return {
        "file": file_data["file"],
        "format": file_data.get("format"),
        "column_headers": column_headers,
        "revenue_by_month":      [round(v, 2) for v in revenue_by_month],
        "expenses_by_month":     [round(v, 2) for v in expenses_by_month],
        "computed_noi_by_month": computed_noi_by_month,
        "total_revenue":         round(revenue_by_month[-1], 2) if column_headers else 0,
        "total_expenses":        round(expenses_by_month[-1], 2) if column_headers else 0,
        "computed_total_noi":    round(computed_noi_by_month[-1], 2) if column_headers else 0,
        "skipped_rows":          skipped_rows,
        "unclassified_rows":     unclassified_rows,
    }


# ═══════════════════════════════════════════════════════════════
#  MAIN — runs both steps sequentially
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    json_files = sorted(AI_MAPPED_DIR.glob("*.json"))

    if not json_files:
        print(f"No files found in {AI_MAPPED_DIR}")
        print("Run find_mapping.py first to generate ai_mapped outputs.")
        sys.exit(0)

    print(f"Found {len(json_files)} file(s) in {AI_MAPPED_DIR}\n")

    classification = load_classification()

    # ── Step 1: Extract actual NOI ────────────────────────────────────────────
    print("── Step 1: Extracting actual NOI ──────────────────────────────────")
    actual_results = {}

    for jfile in json_files:
        with open(jfile) as f:
            file_data = json.load(f)

        result = extract_actual_noi(file_data)
        actual_results[jfile.name] = result

        out_path = ACTUAL_NOI_DIR / jfile.name
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        if result["noi_found"]:
            noi = result["noi_row"]
            print(f"  {result['file']}")
            print(f"    NOI row:  '{noi['description']}' (row {noi['row_number']})")
            print(f"    Annual:   ${noi['total']:,.2f}")
        else:
            print(f"  {result['file']}")
            print(f"    ⚠ {result['error']}")

    print(f"\nSaved actual NOI files → {ACTUAL_NOI_DIR}\n")

    # ── Step 2: Compute NOI from mapped rows ──────────────────────────────────
    print("── Step 2: Computing NOI from mapped rows ─────────────────────────")

    for jfile in json_files:
        with open(jfile) as f:
            file_data = json.load(f)

        result = compute_noi(file_data, classification)

        out_path = COMPUTED_NOI_DIR / jfile.name
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        print(f"  {result['file']}")
        print(f"    Total Revenue:   ${result['total_revenue']:>15,.2f}")
        print(f"    Total Expenses:  ${result['total_expenses']:>15,.2f}")
        print(f"    Computed NOI:    ${result['computed_total_noi']:>15,.2f}")
        if result["skipped_rows"]:
            print(f"    Skipped rows:    {len(result['skipped_rows'])} (capex/below-NOI)")
        if result["unclassified_rows"]:
            print(f"    ⚠ Unclassified: {len(result['unclassified_rows'])} rows (excluded from calculation)")

    print(f"\nSaved computed NOI files → {COMPUTED_NOI_DIR}")
