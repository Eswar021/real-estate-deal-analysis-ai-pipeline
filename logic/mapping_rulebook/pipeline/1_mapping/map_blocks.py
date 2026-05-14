"""
map_blocks.py — Step 2 of the pipeline

Reads the block_detection_results.json (output of detect_blocks),
looks up each data row's description in the mapping rulebook,
and produces mapped_block_results.json with added mapping info.

Pipeline:
  detect_blocks.py → block_detection_results.json
  map_blocks.py    → mapped_block_results.json   (this script)
  results_to_excel.py → Excel files
"""

import json
import sys
from pathlib import Path

# Add project root to sys.path so we can import config
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    BLOCK_DETECTION_DIR,
    AUTO_MAPPED_DIR
)
from config.rulebook_runtime import get_active_rulebook_name, get_active_rulebook_path

ACTIVE_RULEBOOK_PATH = get_active_rulebook_path()
ACTIVE_RULEBOOK_NAME = get_active_rulebook_name()


# ── Build reverse lookup from the rulebook ──
def build_reverse_map(rulebook_path):
    with open(rulebook_path, "r") as f:
        rulebook = json.load(f)

    reverse_map = {}
    for mapping_key, descriptions in rulebook.items():
        for desc in descriptions:
            reverse_map[desc.strip().lower()] = mapping_key
    return reverse_map


def find_mapping(description, reverse_map):
    return reverse_map.get(description.strip().lower(), None)


# ── Main mapping logic ──
def map_results(entry, reverse_map):
    """
    Takes a single block detection result and adds mapping info to each row.
    For data rows: looks up the mapping from the rulebook.
    For non-data rows (header/subtotal): mapping is None, not_found is False.
    """
    mapped_entry = {
        "file": entry["file"],
        "file_path": entry.get("file_path", ""),
        "format": entry["format"],
        "data_start_row": entry["data_start_row"],
        "column_headers": entry.get("column_headers", []),
        "summary": dict(entry["summary"]),  # copy
        "rows": []
    }

    mapped_count = 0
    unmapped_count = 0

    for row in entry["rows"]:
        mapped_row = dict(row)  # copy all existing keys

        if row["type"] == "data":
            mapping = find_mapping(row["description"], reverse_map)
            mapped_row["mapping"] = mapping
            mapped_row["not_found"] = mapping is None

            if mapping:
                mapped_count += 1
            else:
                unmapped_count += 1
        else:
            # Headers and subtotals don't need mapping lookup
            mapped_row["mapping"] = None
            mapped_row["not_found"] = False

        mapped_entry["rows"].append(mapped_row)

    # Add mapping stats to summary
    mapped_entry["summary"]["mapped"] = mapped_count
    mapped_entry["summary"]["unmapped"] = unmapped_count

    return mapped_entry


if __name__ == "__main__":
    # ── Build reverse lookup ──
    reverse_map = build_reverse_map(ACTIVE_RULEBOOK_PATH)
    print(f"Rulebook loaded ({ACTIVE_RULEBOOK_NAME}): {len(reverse_map)} descriptions mapped")
    print(f"  Source: {ACTIVE_RULEBOOK_PATH}\n")

    json_files = sorted(list(BLOCK_DETECTION_DIR.glob("*.json")))
    print(f"Found {len(json_files)} file(s) in block_detection_results")

    for f in json_files:
        with open(f, "r") as fp:
            entry = json.load(fp)
            
        mapped_entry = map_results(entry, reverse_map)
        
        s = mapped_entry["summary"]
        print(f"  {mapped_entry['file']}")
        print(f"    Data: {s['data_rows']} | Mapped: {s['mapped']} | Unmapped: {s['unmapped']}")

        out_path = AUTO_MAPPED_DIR / f.name
        with open(out_path, "w") as fp:
            json.dump(mapped_entry, fp, indent=2)
        
    print(f"\n✅ Saved mapped results → {AUTO_MAPPED_DIR}")
