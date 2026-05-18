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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.paths import BLOCK_DETECTION_DIR, AUTO_MAPPED_DIR
from config.rulebook_runtime import get_active_rulebook_name, get_active_rulebook_path
from config.rulebook_utils import load_rulebook, normalize_lookup_key

ACTIVE_RULEBOOK_PATH = get_active_rulebook_path()
ACTIVE_RULEBOOK_NAME = get_active_rulebook_name()


def match_contextual_rule(entry, row):
    """
    Resolve a contextual rulebook entry to a single mapping.

    rule_type = "statement_side": uses the row's statement_side (detected from
    the raw T12 file structure by detect_blocks) to pick the correct mapping.

    rule_type = "section_rule": checks if any section keyword appears in the
    row's section_path, falls back to the default_mapping.
    """
    if entry["rule_type"] == "statement_side":
        side = row.get("statement_side")
        mapping = entry["conditions"].get(side)
        return mapping, side

    if entry["rule_type"] == "section_rule":
        section_parts = row.get("section_path") or []
        if section_parts:
            section_context = " > ".join(part.strip().lower() for part in section_parts if part)
        else:
            section_context = (row.get("section_context") or "").strip().lower()
        for section_rule in entry["section_rules"]:
            if section_rule["section_contains"] in section_context:
                return section_rule["mapping"], row.get("statement_side")
        return entry["default_mapping"], row.get("statement_side")

    raise ValueError(f"Unknown contextual rule type: {entry['rule_type']}")


def build_match_result(row, rulebook):
    key = normalize_lookup_key(row["description"])
    statement_side = row.get("statement_side")

    if key in rulebook["certain"]:
        entry = rulebook["certain"][key]
        return {
            "mapping": entry["mapping"],
            "not_found": False,
            "mapping_source": "certain",
            "statement_side": statement_side,
        }

    if key in rulebook["contextual"]:
        entry = rulebook["contextual"][key]
        mapping, ctx_side = match_contextual_rule(entry, row)
        if mapping:
            return {
                "mapping": mapping,
                "not_found": False,
                "mapping_source": "contextual",
                "statement_side": ctx_side,
                "client_review_note": entry.get("review_note"),
            }
        return {
            "mapping": None,
            "not_found": True,
            "mapping_source": "contextual_unmatched",
            "statement_side": ctx_side,
            "client_review_note": entry.get("review_note"),
        }

    if key in rulebook["no_conflict"]:
        entry = rulebook["no_conflict"][key]
        return {
            "mapping": entry["mapping"],
            "not_found": False,
            "mapping_source": "no_conflict",
            "statement_side": statement_side,
        }

    if key in rulebook["unresolved"]:
        entry = rulebook["unresolved"][key]
        result = {
            "mapping": None,
            "not_found": True,
            "mapping_source": "unresolved",
            "statement_side": statement_side,
            "client_review_note": entry.get("review_note"),
            "unresolved_reason_type": entry.get("reason_type"),
        }
        if "historical_candidate_mappings" in entry:
            result["historical_candidate_mappings"] = entry["historical_candidate_mappings"]
            result["historical_statement_sides"] = entry.get("historical_statement_sides", [])
            result["historical_section_paths"] = entry.get("historical_section_paths", [])
        return result

    return {
        "mapping": None,
        "not_found": True,
        "mapping_source": "unknown",
        "statement_side": statement_side,
    }


def map_results(entry, rulebook):
    mapped_entry = {
        "file": entry["file"],
        "file_path": entry.get("file_path", ""),
        "format": entry["format"],
        "data_start_row": entry["data_start_row"],
        "column_headers": entry.get("column_headers", []),
        "summary": dict(entry["summary"]),
        "rows": [],
    }

    mapped_count = 0
    unmapped_count = 0

    for row in entry["rows"]:
        mapped_row = dict(row)

        if row["type"] == "data":
            match_result = build_match_result(row, rulebook)
            mapped_row.update(match_result)
            if match_result["mapping"] is not None:
                mapped_count += 1
            else:
                unmapped_count += 1
        else:
            mapped_row["mapping"] = None
            mapped_row["not_found"] = False
            mapped_row["mapping_source"] = None

        mapped_entry["rows"].append(mapped_row)

    mapped_entry["summary"]["mapped"] = mapped_count
    mapped_entry["summary"]["unmapped"] = unmapped_count

    return mapped_entry


if __name__ == "__main__":
    rulebook = load_rulebook(ACTIVE_RULEBOOK_PATH)

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

        mapped_entry = map_results(entry, rulebook=rulebook)

        s = mapped_entry["summary"]
        print(f"  {mapped_entry['file']}")
        print(f"    Data: {s['data_rows']} | Mapped: {s['mapped']} | Unmapped: {s['unmapped']}")

        out_path = AUTO_MAPPED_DIR / f.name
        with open(out_path, "w") as fp:
            json.dump(mapped_entry, fp, indent=2)

    print(f"\nSaved mapped results → {AUTO_MAPPED_DIR}")
