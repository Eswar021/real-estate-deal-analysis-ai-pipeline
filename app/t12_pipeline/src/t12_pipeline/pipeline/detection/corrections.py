"""
corrections.py — UI correction layer

Applies user corrections to an annotated-blocks entry:
  1. Clears old is_total_revenue / is_total_expense / is_noi flags
     (only for the flags being corrected — partial corrections are supported)
  2. Sets new flags on the rows the user chose
  3. Re-walks all rows and reassigns statement_side using the same
     two-flag state machine as detect_blocks

Does NOT reopen the original Excel file — works entirely from the JSON.
Called by the UI pipeline bridge; not part of the automated pipeline.

Usage (standalone test):
    python src/pipeline/1_detection/corrections.py <annotated_blocks_json>
    python src/pipeline/1_detection/corrections.py <json> --total-revenue-row 61
    python src/pipeline/1_detection/corrections.py <json> --noi-row 228 --out corrected.json
"""

import argparse
import copy
import json
from pathlib import Path

from t12_pipeline.pipeline.detection.compute_noi import compute_noi, extract_actual_noi
from t12_pipeline.pipeline.detection.compare_noi import compare


def apply_corrections(entry: dict, corrections: dict) -> dict:
    """
    Apply user corrections to an annotated-blocks entry.

    corrections = {
        "total_revenue_row": int | None,  # row number to mark as is_total_revenue
        "total_expense_row": int | None,  # row number to mark as is_total_expense
        "noi_row":           int | None,  # row number to mark as is_noi
    }

    Pass None for any key you don't want to change — those flags are left as-is.
    Returns a new dict (deep copy) — does not mutate the input.
    Raises ValueError if a given row number does not exist in the entry.
    """
    entry = copy.deepcopy(entry)
    rows  = entry.get("rows", [])

    total_revenue_row = corrections.get("total_revenue_row")
    total_expense_row = corrections.get("total_expense_row")
    noi_row_number    = corrections.get("noi_row")

    # Validate row numbers exist before touching any flags
    existing_rows = {r["row"] for r in rows}
    for label, rn in [
        ("total_revenue_row", total_revenue_row),
        ("total_expense_row", total_expense_row),
        ("noi_row",           noi_row_number),
    ]:
        if rn is not None and rn not in existing_rows:
            raise ValueError(f"corrections['{label}']={rn} does not exist in this file")

    # Step 1: clear existing flags — only for the flags being corrected
    for row in rows:
        if total_revenue_row is not None:
            row["is_total_revenue"] = False
        if total_expense_row is not None:
            row["is_total_expense"] = False
        if noi_row_number is not None:
            row["is_noi"] = False

    # Step 2: set new flags on the corrected rows
    for row in rows:
        rn = row.get("row")
        if total_revenue_row is not None and rn == total_revenue_row:
            row["is_total_revenue"] = True
        if total_expense_row is not None and rn == total_expense_row:
            row["is_total_expense"] = True
        if noi_row_number is not None and rn == noi_row_number:
            row["is_noi"] = True

    # Step 3: re-walk all rows and reassign statement_side.
    # Mirrors the two-flag state machine in detect_blocks.classify_file exactly:
    # subtotals get statement_side from the state BEFORE the flip.
    income_phase_complete = False
    capex_phase_complete  = False

    for row in rows:
        row_type = row.get("type")

        if row_type == "empty":
            continue

        if row_type == "subtotal":
            if capex_phase_complete:
                row["statement_side"] = "capex"
            elif income_phase_complete:
                row["statement_side"] = "expense"
            else:
                row["statement_side"] = "revenue"

            if not income_phase_complete and row.get("is_total_revenue"):
                income_phase_complete = True
            elif income_phase_complete and not capex_phase_complete and row.get("is_noi"):
                capex_phase_complete = True

        elif row_type == "data":
            if capex_phase_complete:
                row["statement_side"] = "capex"
            elif income_phase_complete:
                row["statement_side"] = "expense"
            else:
                row["statement_side"] = "revenue"

        # headers: no statement_side field, leave untouched

    return entry


def recompute_noi(entry: dict) -> dict:
    """
    Run compute_noi + compare_noi on a corrected annotated-blocks entry.
    Returns {"actual": ..., "computed": ..., "comparison": ...}.
    """
    actual     = extract_actual_noi(entry)
    computed   = compute_noi(entry)
    comparison = compare(actual, computed)
    return {"actual": actual, "computed": computed, "comparison": comparison}


# ═══════════════════════════════════════════════════════════════
#  STANDALONE TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apply subtotal corrections and recompute NOI from an annotated-blocks JSON."
    )
    parser.add_argument("json_path", help="Path to an annotated_blocks JSON file")
    parser.add_argument("--total-revenue-row", type=int, default=None, metavar="ROW")
    parser.add_argument("--total-expense-row", type=int, default=None, metavar="ROW")
    parser.add_argument("--noi-row",           type=int, default=None, metavar="ROW")
    parser.add_argument("--out", default=None,
                        help="Write corrected JSON to this path (optional)")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"File not found: {json_path}")

    with open(json_path) as f:
        entry = json.load(f)

    print(f"File: {entry.get('file', json_path.name)}")
    print(f"Rows: {len(entry.get('rows', []))}\n")

    # Show current flags
    print("=== BEFORE ===")
    flag_keys = ("is_total_revenue", "is_total_expense", "is_noi")
    for row in entry.get("rows", []):
        active = [k for k in flag_keys if row.get(k)]
        if active:
            side = row.get("statement_side", "?")
            print(f"  Row {row['row']:3d}  [{side:<7}]  {row['description'][:55]:<55}  {active}")

    corrections = {
        "total_revenue_row": args.total_revenue_row,
        "total_expense_row": args.total_expense_row,
        "noi_row":           args.noi_row,
    }

    any_correction = any(v is not None for v in corrections.values())
    if not any_correction:
        print("\n(No --total-revenue-row / --total-expense-row / --noi-row given.")
        print(" Running as dry-run: recomputing NOI from existing flags.)\n")

    corrected = apply_corrections(entry, corrections)

    if any_correction:
        print("\n=== AFTER ===")
        for row in corrected.get("rows", []):
            active = [k for k in flag_keys if row.get(k)]
            if active:
                side = row.get("statement_side", "?")
                print(f"  Row {row['row']:3d}  [{side:<7}]  {row['description'][:55]:<55}  {active}")

        # Show statement_side changes
        before_sides = {r["row"]: r.get("statement_side") for r in entry.get("rows", []) if "statement_side" in r}
        after_sides  = {r["row"]: r.get("statement_side") for r in corrected.get("rows", []) if "statement_side" in r}
        changed = [
            (rn, before_sides[rn], after_sides[rn])
            for rn in before_sides
            if before_sides.get(rn) != after_sides.get(rn)
        ]
        if changed:
            print(f"\n=== {len(changed)} rows changed statement_side ===")
            rows_by_num = {r["row"]: r for r in corrected["rows"]}
            for rn, old, new in changed[:25]:
                desc = rows_by_num.get(rn, {}).get("description", "")[:40]
                print(f"  Row {rn:3d}  {desc:<40}  {old} → {new}")
            if len(changed) > 25:
                print(f"  ... and {len(changed) - 25} more")
        else:
            print("\nNo statement_side changes.")

    # Recompute NOI
    result = recompute_noi(corrected)
    cmp    = result["comparison"]
    status = "PASS" if cmp.get("overall_pass") else "FAIL"

    totals = cmp.get("totals") or {}
    noi_tot = totals.get("noi") or {}
    rev_tot = totals.get("revenue") or {}
    exp_tot = totals.get("expense") or {}

    print(f"\n=== NOI recomputation: {status} ===")
    print(f"  Actual NOI:   ${(noi_tot.get('actual')   or 0):>15,.2f}")
    print(f"  Computed NOI: ${(noi_tot.get('computed') or 0):>15,.2f}")
    print(f"  Difference:   ${(noi_tot.get('abs_diff') or 0):>15,.2f}")

    if rev_tot.get("actual") is not None:
        print(f"  Revenue:      actual=${rev_tot['actual']:>12,.2f}  computed=${rev_tot['computed']:>12,.2f}  "
              f"diff=${rev_tot['diff']:>8,.2f}  {'OK' if rev_tot['match'] else '!!'}")
    if exp_tot.get("actual") is not None:
        print(f"  Expense:      actual=${exp_tot['actual']:>12,.2f}  computed=${exp_tot['computed']:>12,.2f}  "
              f"diff=${exp_tot['diff']:>8,.2f}  {'OK' if exp_tot['match'] else '!!'}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(corrected, f, indent=2)
        print(f"\nCorrected JSON written to: {out_path}")
