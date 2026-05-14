"""
extract_mappings_v2.py — Rulebook V2 Pipeline Step 1

Reads all human-reviewed xlsm source files and extracts, per row:
  - row_description  : the vendor text from the T12
  - auto_mapping     : what the algorithm suggested
  - override         : what the human typed to override (null if no override)
  - final_mapping    : the mapping that was actually used
  - source_type      : "override" if a human override was set, else "auto"

This richer extraction (vs v1's Final_Mapping-only approach) lets the v2
rulebook builder prioritize human overrides over auto-mapped entries when
the same description appears in multiple files with different mappings.

Input:  data/mapped_T12_docs/t12_docs/*.xlsm
        data/mapped_T12_docs/new_t12_docs/*.xlsm
Output: output_docs/<date>/0_build_rulebook/extracted_mappings_v2/<filename>.json
        (one per source file)

Run before build_rulebook_v2.py.
"""

import json
import openpyxl
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    MAPPED_T12_DOCS_DIR,
    NEW_MAPPED_T12_DOCS_DIR,
    EXTRACTED_MAPPINGS_V2_DIR,
)

REQUIRED_COLS = [
    "Row Description (from T12)",
    "Auto Mapping",
    "OVERRIDE",
    "Final_Mapping",
]


def normalize(val):
    """Strip whitespace and title-case a string value; return None for non-strings or blanks."""
    if not isinstance(val, str):
        return None
    s = val.strip()
    return s.title() if s else None


def find_anchor_row(ws):
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and isinstance(cell.value, str) and "COMPLETE MAPPING HERE" in cell.value.upper():
                return cell.row
    return None


def extract_file(file_path):
    """
    Extract all mapping rows from a single xlsm file.
    Returns a dict ready for JSON output, or raises on unrecoverable errors.
    """
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)

    if "Financials" not in wb.sheetnames:
        wb.close()
        raise ValueError("No 'Financials' sheet found")

    ws = wb["Financials"]
    anchor_row = find_anchor_row(ws)
    if not anchor_row:
        wb.close()
        raise ValueError("Anchor row ('COMPLETE MAPPING HERE') not found")

    raw_rows = list(ws.iter_rows(min_row=anchor_row + 1, values_only=True))
    wb.close()

    if not raw_rows:
        raise ValueError("No data rows below anchor row")

    # Trim to actual table boundary: stop at first data row where the Index
    # column (col 0) is empty — same boundary logic as the original create_mappings.py.
    # Rows beyond this are other sheet content that must not be included.
    all_rows = [raw_rows[0]]  # keep header row unconditionally
    for data_row in raw_rows[1:]:
        if not data_row or data_row[0] is None:
            break
        all_rows.append(data_row)

    headers = all_rows[0]

    # Locate required columns by header name
    col_idx = {}
    for col_name in REQUIRED_COLS:
        try:
            col_idx[col_name] = headers.index(col_name)
        except ValueError:
            raise ValueError(f"Required column '{col_name}' not found in header row")

    rows_out = []
    for data_row in all_rows[1:]:
        desc     = normalize(data_row[col_idx["Row Description (from T12)"]]
                             if col_idx["Row Description (from T12)"] < len(data_row) else None)
        auto_map = normalize(data_row[col_idx["Auto Mapping"]]
                             if col_idx["Auto Mapping"] < len(data_row) else None)
        override = normalize(data_row[col_idx["OVERRIDE"]]
                             if col_idx["OVERRIDE"] < len(data_row) else None)
        final    = normalize(data_row[col_idx["Final_Mapping"]]
                             if col_idx["Final_Mapping"] < len(data_row) else None)

        # Skip rows with no description or no final mapping
        if not desc or not final:
            continue

        # Exclude structural pseudo-mappings inserted by the algorithm
        if final in ("Likely Header", "Likely Subtotal"):
            continue

        source_type = "override" if override else "auto"

        rows_out.append({
            "row_description": desc,
            "auto_mapping":    auto_map,
            "override":        override,
            "final_mapping":   final,
            "source_type":     source_type,
        })

    return {
        "file":          file_path.name,
        "total_rows":    len(rows_out),
        "override_rows": sum(1 for r in rows_out if r["source_type"] == "override"),
        "auto_rows":     sum(1 for r in rows_out if r["source_type"] == "auto"),
        "rows":          rows_out,
    }


if __name__ == "__main__":
    xlsm_files = (
        sorted(MAPPED_T12_DOCS_DIR.glob("*.xlsm")) +
        sorted(NEW_MAPPED_T12_DOCS_DIR.glob("*.xlsm"))
    )
    xlsm_files = [f for f in xlsm_files if not f.name.startswith("~$")]

    print(f"Found {len(xlsm_files)} xlsm source file(s)\n")

    ok_count = 0
    err_count = 0

    for fpath in xlsm_files:
        try:
            result = extract_file(fpath)
            out_path = EXTRACTED_MAPPINGS_V2_DIR / fpath.with_suffix(".json").name
            with open(out_path, "w") as f:
                json.dump(result, f, indent=2)
            print(f"  {result['file']}")
            print(f"    Rows: {result['total_rows']}  "
                  f"(override: {result['override_rows']}, auto: {result['auto_rows']})")
            ok_count += 1
        except Exception as e:
            print(f"  ERROR — {fpath.name}: {e}")
            err_count += 1

    print(f"\nDone: {ok_count} succeeded, {err_count} failed")
    print(f"Saved to: {EXTRACTED_MAPPINGS_V2_DIR}")
