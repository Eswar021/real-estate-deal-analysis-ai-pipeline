"""
compute_noi.py — Stage 1c

Produces two parallel measurements of every T12 file:

  actual_noi.json   (vendor-reported, top-down — read from is_total_* subtotal rows)
      revenue: { by_month, total, row_number, description }
      expense: { by_month, total, sources: [{row_number, description}, ...] }
      noi:     { by_month, total, row_number, description }

  computed_noi.json (our row method, bottom-up — sum DATA rows by statement_side)
      revenue: { by_month, total }
      expense: { by_month, total }
      noi:     { by_month, total }
      skipped_rows, unmapped_rows

Same three measurements on each side → compare_noi can pair them directly.

Reads:
    manifest["l1"]["paths"]["annotated_blocks_dir"]

Writes:
    manifest["l1"]["paths"]["actual_noi_dir"]
    manifest["l1"]["paths"]["computed_noi_dir"]

Does not call an LLM.
"""

import json
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
#  EXTRACT ACTUAL (vendor-reported, top-down)
# ═══════════════════════════════════════════════════════════════

def _find_primary_flagged_row(rows, flag: str):
    """Pick the bottom-most subtotal flagged `flag` that carries numeric values."""
    candidates = [r for r in rows if r.get(flag) and r.get("type") == "subtotal"]
    for row in reversed(candidates):
        if any(isinstance(v, (int, float)) for v in row.get("values", [])):
            return row
    return candidates[0] if candidates else None


def _all_flagged_rows(rows, flag: str):
    """Every subtotal row flagged `flag` (used for expense, which may split into multiple subtotals)."""
    return [r for r in rows if r.get(flag) and r.get("type") == "subtotal"]


def _values_with_last(values, n_cols):
    """Return (per-month list of size n_cols with None for non-numeric, last numeric value)."""
    by_month = [v if isinstance(v, (int, float)) else None for v in values][:n_cols]
    by_month += [None] * (n_cols - len(by_month))
    numeric = [v for v in values if isinstance(v, (int, float))]
    total = numeric[-1] if numeric else None
    return by_month, total


def _sum_rows_by_month(matching_rows, n_cols):
    """Sum matching rows column-wise. Returns (by_month, total). Skips non-numeric cells."""
    by_month = [0.0] * n_cols
    saw_any  = False
    for r in matching_rows:
        values = r.get("values", [])
        for i in range(min(n_cols, len(values))):
            v = values[i]
            if isinstance(v, (int, float)):
                by_month[i] += v
                saw_any = True
    if not saw_any:
        return [None] * n_cols, None
    rounded = [round(v, 2) for v in by_month]
    return rounded, rounded[-1] if rounded else None


def extract_actual_noi(file_data):
    """
    Pulls vendor-reported revenue/expense/NOI directly from the flagged subtotal rows.

    Revenue and NOI: take the primary flagged row (bottom-most one with numeric values).
    Expense: sum across ALL is_total_expense rows — files like Pebble Brook split
    expenses into Controllable + Non-Controllable and the grand total = sum of both.
    """
    rows = file_data.get("rows", [])
    column_headers = file_data.get("column_headers", [])
    n_cols = len(column_headers)

    rev_row = _find_primary_flagged_row(rows, "is_total_revenue")
    noi_row = _find_primary_flagged_row(rows, "is_noi")
    exp_rows = _all_flagged_rows(rows, "is_total_expense")

    def _block_from_single(row):
        if row is None:
            return None
        by_month, total = _values_with_last(row.get("values", []), n_cols)
        return {
            "by_month":    by_month,
            "total":       total,
            "row_number":  row["row"],
            "description": row["description"],
        }

    def _block_from_many(matching_rows):
        if not matching_rows:
            return None
        by_month, total = _sum_rows_by_month(matching_rows, n_cols)
        return {
            "by_month": by_month,
            "total":    total,
            "sources":  [{"row_number": r["row"], "description": r["description"]} for r in matching_rows],
        }

    return {
        "file":           file_data["file"],
        "format":         file_data.get("format"),
        "column_headers": column_headers,
        "revenue":        _block_from_single(rev_row),
        "expense":        _block_from_many(exp_rows),
        "noi":            _block_from_single(noi_row),
    }


# ═══════════════════════════════════════════════════════════════
#  COMPUTE (row method, bottom-up)
# ═══════════════════════════════════════════════════════════════

def compute_noi(file_data):
    """
    Sum all DATA rows by statement_side. No mapping required —
    statement_side from detect_blocks alone determines revenue vs expense.
    Capex rows are skipped (below-NOI-line items).
    """
    column_headers = file_data.get("column_headers", [])
    n_cols = len(column_headers)

    revenue_by_month = [0.0] * n_cols
    expense_by_month = [0.0] * n_cols
    skipped_rows = []
    unmapped_rows = []

    for row in file_data.get("rows", []):
        if row["type"] != "data":
            continue
        values = row.get("values", [])
        if not values:
            continue

        side = row.get("statement_side")
        if side == "capex":
            skipped_rows.append({"row": row["row"], "description": row["description"]})
            continue
        if side not in ("revenue", "expense"):
            unmapped_rows.append({"row": row["row"], "description": row["description"], "statement_side": side})
            continue

        for i in range(min(n_cols, len(values))):
            v = values[i]
            if not isinstance(v, (int, float)):
                continue
            if side == "revenue":
                revenue_by_month[i] += v
            else:
                expense_by_month[i] += v

    revenue_by_month = [round(v, 2) for v in revenue_by_month]
    expense_by_month = [round(v, 2) for v in expense_by_month]
    noi_by_month     = [round(revenue_by_month[i] - expense_by_month[i], 2) for i in range(n_cols)]

    return {
        "file":           file_data["file"],
        "format":         file_data.get("format"),
        "column_headers": column_headers,
        "revenue":        {"by_month": revenue_by_month, "total": revenue_by_month[-1] if n_cols else 0},
        "expense":        {"by_month": expense_by_month, "total": expense_by_month[-1] if n_cols else 0},
        "noi":            {"by_month": noi_by_month,     "total": noi_by_month[-1]     if n_cols else 0},
        "skipped_rows":   skipped_rows,
        "unmapped_rows":  unmapped_rows,
    }


# ═══════════════════════════════════════════════════════════════
#  STANDALONE BATCH
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from t12_pipeline.config.paths import MANIFEST_PATH
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

        print(f"  {computed['file']}  NOI: ${computed['noi']['total']:,.2f}")
