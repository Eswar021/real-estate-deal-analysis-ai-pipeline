import json
import pandas as pd
import sys
from pathlib import Path

# Add project root to sys.path so we can import config
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import RULEBOOK_EXCEL_PATH
from config.rulebook_runtime import get_active_rulebook_name, get_active_rulebook_path
from config.rulebook_utils import flatten_rulebook_rows

# ── Paths ────────────────────────────────────────────────────────────────────
INPUT_JSON = get_active_rulebook_path()
OUTPUT_XLS = RULEBOOK_EXCEL_PATH
ACTIVE_RULEBOOK_NAME = get_active_rulebook_name()

# ── Load JSON ────────────────────────────────────────────────────────────────
with open(INPUT_JSON, "r", encoding="utf-8") as f:
    rulebook = json.load(f)

# ── Flatten rulebook rows across all supported schemas ───────────────────────
rows = []
for entry in flatten_rulebook_rows(rulebook):
    rows.append({
        "Rulebook Section": entry["rulebook_section"],
        "Row Description": entry["row_description"],
        "Final Mapping": entry["mapping"],
        "Rule Type": entry["rule_type"],
        "Rule Detail": entry["rule_detail"],
    })

df = pd.DataFrame(
    rows,
    columns=["Rulebook Section", "Row Description", "Final Mapping", "Rule Type", "Rule Detail"],
)

# ── Write to Excel ───────────────────────────────────────────────────────────
with pd.ExcelWriter(OUTPUT_XLS, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Mapping Rulebook")

    # ── Auto-fit column widths ────────────────────────────────────────────
    ws = writer.sheets["Mapping Rulebook"]
    for col_cells in ws.columns:
        max_len = max(len(str(cell.value)) for cell in col_cells if cell.value)
        ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 80)

print(f"✅  Done! {len(df):,} rows written → {OUTPUT_XLS}")
print(f"   Source rulebook: {ACTIVE_RULEBOOK_NAME} -> {INPUT_JSON}")
