import openpyxl
import pandas as pd
from collections import defaultdict
import json
import glob
import os

import sys
from pathlib import Path

# Add project root to sys.path so we can import config
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    MAPPED_T12_DOCS_DIR,
    NEW_MAPPED_T12_DOCS_DIR,
    RULEBOOK_DB_PATH,
    RULEBOOK_V1_OUTPUT_PATH,
)

# ── 1. Find anchor row ──
def find_anchor_row(ws):
    for row in range(1, ws.max_row + 1):
        val = ws.cell(row=row, column=24).value
        if val and isinstance(val, str) and "COMPLETE MAPPING HERE" in val.upper():
            return row
    return None


# ── 2. Find table boundaries ──
def find_table_boundaries(ws, header_row):
    # Column boundaries
    start_col = None
    end_col = None
    for col in range(1, ws.max_column + 1):
        val = ws.cell(row=header_row, column=col).value
        if val is not None:
            if start_col is None:
                start_col = col
            end_col = col

    # Row boundary using Index column (col 1)
    end_row = header_row
    for row in range(header_row + 1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value is not None:
            end_row = row
        else:
            break

    return start_col, end_col, end_row


# ── 3. Load raw table into DataFrame ──
def load_raw_table(ws, header_row, start_col, end_col, end_row):
    data = []
    for row in ws.iter_rows(min_row=header_row, max_row=end_row, min_col=start_col, max_col=end_col, values_only=True):
        data.append(row)

    headers = data[0]
    df_raw = pd.DataFrame(data[1:], columns=headers)
    return df_raw


# ── 4. Extract mapping columns ──
def extract_mapping_df(df_raw):
    df = df_raw[["Row Description (from T12)", "Auto Mapping", "OVERRIDE", "Final_Mapping"]].dropna(how="all")
    return df


# ── 5. Process a single file end-to-end ──
def process_file(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb["Financials"]

    anchor_row = find_anchor_row(ws)
    header_row = anchor_row + 1
    start_col, end_col, end_row = find_table_boundaries(ws, header_row)
    df_raw = load_raw_table(ws, header_row, start_col, end_col, end_row)
    df = extract_mapping_df(df_raw)

    wb.close()
    print(f"  ✓ {file_path} -> {len(df)} rows")
    return df

# ── Normalize df before building rulebook ──
def normalize_df(df):
    df = df.copy()
    df["Row Description (from T12)"] = df["Row Description (from T12)"].str.strip().str.title()
    df["Auto Mapping"] = df["Auto Mapping"].str.strip().str.title()
    df["Final_Mapping"] = df["Final_Mapping"].str.strip().str.title()
    df["OVERRIDE"] = df["OVERRIDE"].str.strip().str.title()
    return df


if __name__ == "__main__":
    import json
    import os
    from collections import defaultdict

    # files = [
    #     "./t12_docs/02252026_Willows of Coventry_V4 (1).xlsm",
    #     "./t12_docs/02242026_Grande Reserve at Geist_V3- VM.xlsm",
    #     "./t12_docs/03092026_The Flats at Arrowood_V4 (FULL BUDGET).xlsm",
    #     "./t12_docs/03092026_The Tatum_V4 (assumption).xlsm",
    #     "./t12_docs/03122025_District at Hurstborne_V2.xlsm",
    #     "./t12_docs/260312_Melville Apartments_V18-HNW BRIDGE.xlsm",
    # ]

    files = sorted([str(f) for f in MAPPED_T12_DOCS_DIR.glob("*.xlsm")
                     if not f.name.startswith("~$")])
    print(files)

    file_2 = sorted([str(f) for f in NEW_MAPPED_T12_DOCS_DIR.glob("*.xlsm")
                      if not f.name.startswith("~$")])

    files.extend(file_2)

    # ── Load read-only baseline rulebook or start fresh ──
    rulebook_path = str(RULEBOOK_DB_PATH)
    global_rulebook = defaultdict(set)

    if os.path.exists(rulebook_path):
        with open(rulebook_path, "r") as f:
            existing = json.load(f)
        for key, values in existing.items():
            normalized_key = key.strip().title() if not key.startswith("__") else key
            for v in values:
                global_rulebook[normalized_key].add(v.strip().title())
        print(f"Loaded existing rulebook with {len(existing)} keys")
    else:
        print("No existing rulebook found, starting fresh")

    # ── Process new files on top of existing rulebook ──
    for file_path in files:
        print(f"Processing: {file_path}")
        df = process_file(file_path)
        df = normalize_df(df)

        df_mapped = df.dropna(subset=["Final_Mapping"])
        for _, row in df_mapped.iterrows():
            global_rulebook[row["Final_Mapping"]].add(row["Row Description (from T12)"])

        # df_headers = df[df["Auto Mapping"] == "Likely Header"]
        # df_subtotals = df[df["Auto Mapping"] == "Likely Subtotal"]
        # for v in df_headers["Row Description (from T12)"]:
        #     global_rulebook["__LIKELY_HEADER__"].add(v)
        # for v in df_subtotals["Row Description (from T12)"]:
        #     global_rulebook["__LIKELY_SUBTOTAL__"].add(v)

    mapping_rulebook = {k: sorted(v) for k, v in sorted(global_rulebook.items())}

    # ── Save built rulebook to output_docs only ──
    with open(RULEBOOK_V1_OUTPUT_PATH, "w") as f:
        json.dump(mapping_rulebook, f, indent=2)
    print(f"Saved rulebook -> {RULEBOOK_V1_OUTPUT_PATH}")
