import json
import pandas as pd
import sys
from pathlib import Path

# Add project root to sys.path so we can import config
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    # RULEBOOK_DB_PATH, 
    RULEBOOK_DB_V2_PATH as RULEBOOK_DB_PATH,
    RULEBOOK_EXCEL_PATH)

# ── Paths ────────────────────────────────────────────────────────────────────
INPUT_JSON = RULEBOOK_DB_PATH
OUTPUT_XLS = RULEBOOK_EXCEL_PATH

# ── Load JSON ────────────────────────────────────────────────────────────────
with open(INPUT_JSON, "r", encoding="utf-8") as f:
    rulebook: dict[str, list[str]] = json.load(f)

# ── Flatten  key → each value as its own row ─────────────────────────────────
rows = []
for final_mapping, descriptions in rulebook.items():
    for desc in descriptions:
        rows.append({"Final Mapping": final_mapping, "Row Description": desc})

df = pd.DataFrame(rows, columns=["Row Description", "Final Mapping"])

# ── Write to Excel ───────────────────────────────────────────────────────────
with pd.ExcelWriter(OUTPUT_XLS, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Mapping Rulebook")

    # ── Auto-fit column widths ────────────────────────────────────────────
    ws = writer.sheets["Mapping Rulebook"]
    for col_cells in ws.columns:
        max_len = max(len(str(cell.value)) for cell in col_cells if cell.value)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 80)

print(f"✅  Done! {len(df):,} rows written → {OUTPUT_XLS}")
