"""
compare_noi.py — Stage 1d

Two verification layers per file:
  1. NOI check: row-method sum (revenue - expense) vs vendor's is_noi subtotal
  2. Revenue accuracy: row-method revenue vs vendor's EGI (is_total_revenue subtotal)
     Implied expense = EGI - actual_noi; compared against row-method expense sum

Reads:
    manifest["l1"]["paths"]["actual_noi_dir"]
    manifest["l1"]["paths"]["computed_noi_dir"]

Writes:
    manifest["l1"]["paths"]["noi_comparison_dir"]

Does not call an LLM.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

TOLERANCE_DOLLARS = 1.0
TOLERANCE_PERCENT = 0.01

# Set STRICT = True for exact comparison (fails on any cent difference).
# Set STRICT = False to allow TOLERANCE_DOLLARS / TOLERANCE_PERCENT slack.
STRICT = True


def _within_tolerance(actual, computed):
    diff = abs(round(actual, 2) - round(computed, 2))
    if STRICT:
        return diff == 0, round(diff, 2), 0
    threshold = max(TOLERANCE_DOLLARS, abs(actual) * TOLERANCE_PERCENT)
    return diff <= threshold, round(diff, 2), round(threshold, 2)


def compare(actual_data, computed_data):
    file_name = actual_data["file"]
    column_headers = actual_data.get("column_headers", [])

    if not actual_data.get("noi_found"):
        return {
            "file": file_name,
            "overall_pass": False,
            "error": actual_data.get("error", "Actual NOI not found"),
            "months": [],
        }

    actual_noi_values   = actual_data["noi_row"]["values"]
    computed_noi_values = computed_data["computed_noi_by_month"]
    revenue_row_values  = computed_data.get("revenue_by_month", [])
    expense_row_values  = computed_data.get("expenses_by_month", [])
    revenue_sub_values  = computed_data.get("revenue_subtotal_by_month", [])

    n = min(len(column_headers), len(actual_noi_values), len(computed_noi_values))

    months = []
    any_noi_fail = False

    for i in range(n):
        actual_noi   = actual_noi_values[i]  if isinstance(actual_noi_values[i],   (int, float)) else 0.0
        computed_noi = computed_noi_values[i] if isinstance(computed_noi_values[i], (int, float)) else 0.0
        row_rev  = revenue_row_values[i] if i < len(revenue_row_values)  and isinstance(revenue_row_values[i],  (int, float)) else None
        row_exp  = expense_row_values[i] if i < len(expense_row_values)  and isinstance(expense_row_values[i],  (int, float)) else None
        vendor_egi = revenue_sub_values[i] if i < len(revenue_sub_values) and isinstance(revenue_sub_values[i], (int, float)) else None

        noi_within, noi_diff, _ = _within_tolerance(actual_noi, computed_noi)
        if not noi_within:
            any_noi_fail = True

        month_entry = {
            "month":    column_headers[i] if i < len(column_headers) else f"Col {i+1}",
            "actual":   round(actual_noi, 2),
            "computed": round(computed_noi, 2),
            "diff":     round(computed_noi - actual_noi, 2),
            "abs_diff": noi_diff,
            "match":    noi_within,
        }

        if vendor_egi is not None and row_rev is not None:
            rev_within, rev_diff, _ = _within_tolerance(vendor_egi, row_rev)
            month_entry["revenue_check"] = {
                "vendor_egi": round(vendor_egi, 2),
                "row_method": round(row_rev, 2),
                "diff":       round(row_rev - vendor_egi, 2),
                "abs_diff":   rev_diff,
                "match":      rev_within,
            }

        if vendor_egi is not None and row_exp is not None:
            implied_exp = vendor_egi - actual_noi
            exp_within, exp_diff, _ = _within_tolerance(implied_exp, row_exp)
            month_entry["expense_check"] = {
                "implied_expense": round(implied_exp, 2),
                "row_method":      round(row_exp, 2),
                "diff":            round(row_exp - implied_exp, 2),
                "abs_diff":        exp_diff,
                "match":           exp_within,
            }

        months.append(month_entry)

    actual_total   = actual_data["noi_row"]["total"]
    computed_total = computed_data["computed_total_noi"]
    total_within, total_diff, total_threshold = _within_tolerance(
        actual_total or 0, computed_total or 0
    )

    result = {
        "file":               file_name,
        "format":             actual_data.get("format"),
        "overall_pass":       not any_noi_fail and total_within,
        "actual_noi_row":     actual_data["noi_row"]["description"],
        "total_actual_noi":   round(actual_total or 0, 2),
        "total_computed_noi": round(computed_total or 0, 2),
        "total_diff":         round((computed_total or 0) - (actual_total or 0), 2),
        "total_abs_diff":     round(total_diff, 2),
        "total_match":        total_within,
        "tolerance_used":     round(total_threshold, 2),
        "skipped_count":      len(computed_data.get("skipped_rows", [])),
        "unmapped_count":     len(computed_data.get("unmapped_rows", [])),
        "months":             months,
    }

    total_rev_sub = computed_data.get("total_revenue_subtotal")
    total_rev_row = computed_data.get("total_revenue")
    total_exp_row = computed_data.get("total_expenses")

    if total_rev_sub is not None and total_rev_row is not None:
        rev_within, rev_diff, _ = _within_tolerance(total_rev_sub, total_rev_row)
        result["total_revenue_check"] = {
            "vendor_egi": round(total_rev_sub, 2),
            "row_method": round(total_rev_row, 2),
            "diff":       round(total_rev_row - total_rev_sub, 2),
            "abs_diff":   rev_diff,
            "match":      rev_within,
        }

    if total_rev_sub is not None and total_exp_row is not None:
        implied_exp = total_rev_sub - (actual_total or 0)
        exp_within, exp_diff, _ = _within_tolerance(implied_exp, total_exp_row)
        result["total_expense_check"] = {
            "implied_expense": round(implied_exp, 2),
            "row_method":      round(total_exp_row, 2),
            "diff":            round(total_exp_row - implied_exp, 2),
            "abs_diff":        exp_diff,
            "match":           exp_within,
        }

    return result


if __name__ == "__main__":
    from config.paths import MANIFEST_PATH
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"No manifest at {MANIFEST_PATH}. Run Stage 0 first.")

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    actual_noi_dir     = Path(manifest["l1"]["paths"]["actual_noi_dir"])
    computed_noi_dir   = Path(manifest["l1"]["paths"]["computed_noi_dir"])
    noi_comparison_dir = Path(manifest["l1"]["paths"]["noi_comparison_dir"])

    actual_files = sorted(actual_noi_dir.glob("*.json"))
    if not actual_files:
        raise FileNotFoundError(f"No files in {actual_noi_dir}. Run compute_noi.py first.")

    print(f"Found {len(actual_files)} file(s)\n")

    pass_count = 0
    fail_count = 0

    for actual_path in actual_files:
        computed_path = computed_noi_dir / actual_path.name
        if not computed_path.exists():
            raise FileNotFoundError(f"Missing computed NOI file: {actual_path.name}")

        with open(actual_path) as f:
            actual_data = json.load(f)
        with open(computed_path) as f:
            computed_data = json.load(f)

        result = compare(actual_data, computed_data)

        out_path = noi_comparison_dir / actual_path.name
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        status = "PASS" if result["overall_pass"] else "FAIL"
        print(f"  {status}  {result['file']}")
        print(f"         Actual NOI:    ${result['total_actual_noi']:>15,.2f}")
        print(f"         Computed NOI:  ${result['total_computed_noi']:>15,.2f}")
        print(f"         Difference:    ${result['total_abs_diff']:>15,.2f}")

        if "total_revenue_check" in result:
            rc = result["total_revenue_check"]
            rc_flag = "OK" if rc["match"] else "!!"
            print(f"         Revenue [{rc_flag}]:  EGI=${rc['vendor_egi']:>12,.2f}  Row=${rc['row_method']:>12,.2f}  Diff=${rc['diff']:>8,.2f}")

        if "total_expense_check" in result:
            ec = result["total_expense_check"]
            ec_flag = "OK" if ec["match"] else "!!"
            print(f"         Expense [{ec_flag}]:  Implied=${ec['implied_expense']:>9,.2f}  Row=${ec['row_method']:>12,.2f}  Diff=${ec['diff']:>8,.2f}")

        if result.get("unmapped_count", 0) > 0:
            print(f"         ! {result['unmapped_count']} rows with no statement_side (informational only)")

        if not result["overall_pass"]:
            fail_count += 1
            failing_months = [m for m in result["months"] if not m["match"]]
            if failing_months:
                print(f"         Months with mismatch ({len(failing_months)}):")
                for m in failing_months:
                    print(f"           {m['month']:<12}  actual=${m['actual']:>12,.2f}  "
                          f"computed=${m['computed']:>12,.2f}  diff=${m['diff']:>10,.2f}")
        else:
            pass_count += 1
        print()

    print("=" * 55)
    print(f"  PASSED: {pass_count}   FAILED: {fail_count}   TOTAL: {pass_count + fail_count}")
    print(f"  Saved comparison files -> {noi_comparison_dir}")
