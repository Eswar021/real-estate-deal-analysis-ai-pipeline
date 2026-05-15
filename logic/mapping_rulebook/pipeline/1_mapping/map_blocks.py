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
    AUTO_MAPPED_DIR,
    HISTORICAL_CONFLICTS_PATH,
    SECTION_SIDE_SUPPORT_PATH,
)
from config.rulebook_runtime import get_active_rulebook_name, get_active_rulebook_path
from config.rulebook_utils import (
    build_section_path_key,
    load_rulebook,
    normalize_lookup_key,
    normalize_section_key,
)

ACTIVE_RULEBOOK_PATH = get_active_rulebook_path()
ACTIVE_RULEBOOK_NAME = get_active_rulebook_name()
ACTIVE_HISTORICAL_CONFLICTS_PATH = HISTORICAL_CONFLICTS_PATH
ACTIVE_SECTION_SIDE_SUPPORT_PATH = SECTION_SIDE_SUPPORT_PATH


def load_historical_conflicts():
    if not ACTIVE_HISTORICAL_CONFLICTS_PATH.exists():
        return {}

    with open(ACTIVE_HISTORICAL_CONFLICTS_PATH, "r") as f:
        payload = json.load(f)

    return payload.get("conflicts", {})


def load_section_side_support():
    if not ACTIVE_SECTION_SIDE_SUPPORT_PATH.exists():
        return {}

    with open(ACTIVE_SECTION_SIDE_SUPPORT_PATH, "r") as f:
        return json.load(f)


def infer_statement_side(row, section_side_support=None):
    section_side_support = section_side_support or {}
    section_path_rules = section_side_support.get("section_path_rules", {})
    nearest_section_rules = section_side_support.get("nearest_section_rules", {})
    top_section_rules = section_side_support.get("top_section_rules", {})

    section_path = row.get("section_path") or []
    if section_path:
        full_path_key = build_section_path_key(section_path)
        if full_path_key and full_path_key in section_path_rules:
            entry = section_path_rules[full_path_key]
            return entry["statement_side"], "section_path"

        nearest_lookup = normalize_section_key(section_path[-1])
        if nearest_lookup in nearest_section_rules:
            entry = nearest_section_rules[nearest_lookup]
            return entry["statement_side"], "nearest_section"

        top_lookup = normalize_section_key(section_path[0])
        if top_lookup in top_section_rules:
            entry = top_section_rules[top_lookup]
            return entry["statement_side"], "top_section"

    section_context = row.get("section_context")
    if section_context:
        nearest_lookup = normalize_section_key(section_context)
        if nearest_lookup in nearest_section_rules:
            entry = nearest_section_rules[nearest_lookup]
            return entry["statement_side"], "nearest_section"

    return None, None


def match_contextual_rule(entry, row, section_side_support=None):
    if entry["rule_type"] == "statement_side":
        side, side_source = infer_statement_side(row, section_side_support)
        mapping = entry["conditions"].get(side)
        return mapping, side, side_source

    if entry["rule_type"] == "section_rule":
        section_parts = row.get("section_path") or []
        if section_parts:
            section_context = " > ".join(part.strip().lower() for part in section_parts if part)
        else:
            section_context = (row.get("section_context") or "").strip().lower()
        for section_rule in entry["section_rules"]:
            if section_rule["section_contains"] in section_context:
                side, side_source = infer_statement_side(row, section_side_support)
                return section_rule["mapping"], side, side_source
        side, side_source = infer_statement_side(row, section_side_support)
        return entry["default_mapping"], side, side_source

    raise ValueError(f"Unknown contextual rule type: {entry['rule_type']}")


def build_match_result(row, rulebook, historical_conflicts, section_side_support):
    key = normalize_lookup_key(row["description"])
    inferred_side, inferred_side_source = infer_statement_side(row, section_side_support)

    if key in rulebook["certain"]:
        entry = rulebook["certain"][key]
        return {
            "mapping": entry["mapping"],
            "not_found": False,
            "mapping_source": "certain",
            "inferred_statement_side": inferred_side,
            "statement_side_source": inferred_side_source,
        }

    if key in rulebook["contextual"]:
        entry = rulebook["contextual"][key]
        mapping, contextual_side, contextual_side_source = match_contextual_rule(entry, row, section_side_support)
        if mapping:
            return {
                "mapping": mapping,
                "not_found": False,
                "mapping_source": "contextual",
                "inferred_statement_side": contextual_side,
                "statement_side_source": contextual_side_source,
                "client_review_note": entry.get("review_note"),
            }
        return {
            "mapping": None,
            "not_found": True,
            "mapping_source": "contextual_unmatched",
            "inferred_statement_side": contextual_side,
            "statement_side_source": contextual_side_source,
            "client_review_note": entry.get("review_note"),
        }

    if key in rulebook["no_conflict"]:
        entry = rulebook["no_conflict"][key]
        return {
            "mapping": entry["mapping"],
            "not_found": False,
            "mapping_source": "no_conflict",
            "inferred_statement_side": inferred_side,
            "statement_side_source": inferred_side_source,
        }

    if key in rulebook["unresolved"]:
        entry = rulebook["unresolved"][key]
        result = {
            "mapping": None,
            "not_found": True,
            "mapping_source": "unresolved",
            "inferred_statement_side": inferred_side,
            "statement_side_source": inferred_side_source,
            "client_review_note": entry.get("review_note"),
            "unresolved_reason_type": entry.get("reason_type"),
        }
        historical = historical_conflicts.get(key)
        if historical:
            result["historical_candidate_mappings"] = historical.get("mappings", [])
            result["historical_statement_sides"] = historical.get("statement_sides", [])
            result["historical_section_paths"] = historical.get("section_paths", [])
        return result

    return {
        "mapping": None,
        "not_found": True,
        "mapping_source": "unknown",
        "inferred_statement_side": inferred_side,
        "statement_side_source": inferred_side_source,
    }


# ── Main mapping logic ──
def map_results(entry, rulebook, historical_conflicts=None, section_side_support=None):
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
            match_result = build_match_result(
                row,
                rulebook,
                historical_conflicts or {},
                section_side_support or {},
            )
            mapped_row.update(match_result)
            mapping = match_result["mapping"]

            if mapping is not None:
                mapped_count += 1
            else:
                unmapped_count += 1
        else:
            # Headers and subtotals don't need mapping lookup
            mapped_row["mapping"] = None
            mapped_row["not_found"] = False
            mapped_row["mapping_source"] = None

        mapped_entry["rows"].append(mapped_row)

    # Add mapping stats to summary
    mapped_entry["summary"]["mapped"] = mapped_count
    mapped_entry["summary"]["unmapped"] = unmapped_count

    return mapped_entry


if __name__ == "__main__":
    rulebook = load_rulebook(ACTIVE_RULEBOOK_PATH)
    historical_conflicts = load_historical_conflicts()
    section_side_support = load_section_side_support()

    summary = rulebook.get("summary", {})
    print(
        f"Rulebook loaded ({ACTIVE_RULEBOOK_NAME}): "
        f"certain={summary.get('certain', 0)}, "
        f"contextual={summary.get('contextual', 0)}, "
        f"no_conflict={summary.get('no_conflict', 0)}, "
        f"unresolved={summary.get('unresolved', 0)}"
    )
    print(f"  Source: {ACTIVE_RULEBOOK_PATH}\n")

    json_files = sorted(list(BLOCK_DETECTION_DIR.glob("*.json")))
    print(f"Found {len(json_files)} file(s) in block_detection_results")

    for f in json_files:
        with open(f, "r") as fp:
            entry = json.load(fp)
            
        mapped_entry = map_results(
            entry,
            rulebook=rulebook,
            historical_conflicts=historical_conflicts,
            section_side_support=section_side_support,
        )
        
        s = mapped_entry["summary"]
        print(f"  {mapped_entry['file']}")
        print(f"    Data: {s['data_rows']} | Mapped: {s['mapped']} | Unmapped: {s['unmapped']}")

        out_path = AUTO_MAPPED_DIR / f.name
        with open(out_path, "w") as fp:
            json.dump(mapped_entry, fp, indent=2)
        
    print(f"\n✅ Saved mapped results → {AUTO_MAPPED_DIR}")
