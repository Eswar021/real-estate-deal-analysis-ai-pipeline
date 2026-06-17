"""
compare_noi.py — Stage 1d

Pairs the actual (vendor-reported) and computed (row method) blocks produced
by compute_noi and emits a symmetric per-month + totals comparison.

Output shape (comparison.json):

    {
        "file": ..., "format": ..., "column_headers": [...],
        "overall_pass": <bool>,                     # NOI-only: totals.noi.match AND every months[i].noi.match
        "tolerance_used": <num>,                    # 0 when STRICT=True
        "months": [
            {
                "month": "...",
                "revenue": {"actual","computed","diff","abs_diff","match"},
                "expense": {"actual","computed","diff","abs_diff","match"},
                "noi":     {"actual","computed","diff","abs_diff","match"}
            }, ...
        ],
        "totals": {
            "revenue": {"actual","computed","diff","abs_diff","match"},
            "expense": {"actual","computed","diff","abs_diff","match"},
            "noi":     {"actual","computed","diff","abs_diff","match"}    # drives overall_pass
        },
        "actual_noi_row":  "<description>",          # convenience; from actual_data.noi.description
        "skipped_count":   <int>,
        "unmapped_count":  <int>
    }

If a measurement's "actual" is missing for a column (vendor didn't provide that
subtotal, e.g. some files have no is_total_expense flag), match is set to null
and that measurement does NOT count toward overall_pass.

Reads:   manifest["l1"]["paths"]["actual_noi_dir"], manifest["l1"]["paths"]["computed_noi_dir"]
Writes:  manifest["l1"]["paths"]["noi_comparison_dir"]
Does not call an LLM.
"""

import json
from pathlib import Path

TOLERANCE_DOLLARS = 1.0
TOLERANCE_PERCENT = 0.01

# Set STRICT = True for exact comparison (fails on any cent difference).
# Set STRICT = False to allow TOLERANCE_DOLLARS / TOLERANCE_PERCENT slack.
STRICT = True


def _threshold(actual_val: float | None) -> float:
    if STRICT:
        return 0
    return max(TOLERANCE_DOLLARS, abs(actual_val or 0) * TOLERANCE_PERCENT)


def _diff_block(actual, computed) -> dict:
    """One {actual, computed, diff, abs_diff, match} entry. Tolerates None actual."""
    if actual is None or computed is None:
        return {
            "actual":   round(actual, 2)   if isinstance(actual,   (int, float)) else None,
            "computed": round(computed, 2) if isinstance(computed, (int, float)) else None,
            "diff":     None,
            "abs_diff": None,
            "match":    None,
        }
    diff_signed = round(computed - actual, 2)
    abs_d       = abs(round(actual, 2) - round(computed, 2))
    threshold   = _threshold(actual)
    return {
        "actual":   round(actual, 2),
        "computed": round(computed, 2),
        "diff":     diff_signed,
        "abs_diff": round(abs_d, 2),
        "match":    abs_d <= threshold,
    }


def _safe_index(seq, i):
    """Return seq[i] if it's a number, else None."""
    if i < 0 or i >= len(seq):
        return None
    v = seq[i]
    return v if isinstance(v, (int, float)) else None


def compare(actual_data: dict, computed_data: dict) -> dict:
    file_name      = actual_data["file"]
    column_headers = actual_data.get("column_headers", [])

    # Vendor-reported (may be None per measurement if file lacks that subtotal)
    a_rev = (actual_data.get("revenue") or {}).get("by_month") or []
    a_exp = (actual_data.get("expense") or {}).get("by_month") or []
    a_noi = (actual_data.get("noi")     or {}).get("by_month") or []

    a_rev_total = (actual_data.get("revenue") or {}).get("total")
    a_exp_total = (actual_data.get("expense") or {}).get("total")
    a_noi_total = (actual_data.get("noi")     or {}).get("total")

    # Computed (always populated; may be 0)
    c_rev = computed_data["revenue"]["by_month"]
    c_exp = computed_data["expense"]["by_month"]
    c_noi = computed_data["noi"]["by_month"]

    c_rev_total = computed_data["revenue"]["total"]
    c_exp_total = computed_data["expense"]["total"]
    c_noi_total = computed_data["noi"]["total"]

    n = len(column_headers)
    months = []
    any_noi_fail = False

    for i in range(n):
        rev_entry = _diff_block(_safe_index(a_rev, i), _safe_index(c_rev, i))
        exp_entry = _diff_block(_safe_index(a_exp, i), _safe_index(c_exp, i))
        noi_entry = _diff_block(_safe_index(a_noi, i), _safe_index(c_noi, i))

        if noi_entry["match"] is False:
            any_noi_fail = True

        months.append({
            "month":   column_headers[i],
            "revenue": rev_entry,
            "expense": exp_entry,
            "noi":     noi_entry,
        })

    totals = {
        "revenue": _diff_block(a_rev_total, c_rev_total),
        "expense": _diff_block(a_exp_total, c_exp_total),
        "noi":     _diff_block(a_noi_total, c_noi_total),
    }

    overall_pass = (totals["noi"]["match"] is True) and (not any_noi_fail)

    return {
        "file":            file_name,
        "format":          actual_data.get("format"),
        "column_headers":  column_headers,
        "overall_pass":    overall_pass,
        "tolerance_used":  _threshold(a_noi_total),
        "months":          months,
        "totals":          totals,
        "actual_noi_row":  (actual_data.get("noi") or {}).get("description"),
        "skipped_count":   len(computed_data.get("skipped_rows", [])),
        "unmapped_count":  len(computed_data.get("unmapped_rows", [])),
    }


if __name__ == "__main__":
    from t12_pipeline.config.paths import MANIFEST_PATH
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

        status   = "PASS" if result["overall_pass"] else "FAIL"
        noi_tot  = result["totals"]["noi"]
        rev_tot  = result["totals"]["revenue"]
        exp_tot  = result["totals"]["expense"]
        print(f"  {status}  {result['file']}")
        print(f"         NOI      actual=${(noi_tot['actual'] or 0):>15,.2f}  computed=${(noi_tot['computed'] or 0):>15,.2f}  diff=${(noi_tot['abs_diff'] or 0):>10,.2f}")
        if rev_tot["actual"] is not None:
            flag = "OK" if rev_tot["match"] else "!!"
            print(f"         Revenue [{flag}] actual=${rev_tot['actual']:>12,.2f}  computed=${rev_tot['computed']:>12,.2f}  diff=${rev_tot['diff']:>8,.2f}")
        if exp_tot["actual"] is not None:
            flag = "OK" if exp_tot["match"] else "!!"
            print(f"         Expense [{flag}] actual=${exp_tot['actual']:>12,.2f}  computed=${exp_tot['computed']:>12,.2f}  diff=${exp_tot['diff']:>8,.2f}")

        if result.get("unmapped_count", 0) > 0:
            print(f"         ! {result['unmapped_count']} rows with no statement_side (informational only)")

        if result["overall_pass"]:
            pass_count += 1
        else:
            fail_count += 1
            failing = [m for m in result["months"] if m["noi"]["match"] is False]
            if failing:
                print(f"         Months with NOI mismatch ({len(failing)}):")
                for m in failing:
                    n = m["noi"]
                    print(f"           {m['month']:<12}  actual=${n['actual']:>12,.2f}  computed=${n['computed']:>12,.2f}  diff=${n['diff']:>10,.2f}")
        print()

    print("=" * 55)
    print(f"  PASSED: {pass_count}   FAILED: {fail_count}   TOTAL: {pass_count + fail_count}")
    print(f"  Saved comparison files -> {noi_comparison_dir}")
