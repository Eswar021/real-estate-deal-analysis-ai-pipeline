"""
build_section_side_support.py

Builds a learned section-to-statement-side support file from the reviewed `.xlsm`
history extraction.

This support artifact is used by Stage 1 only for contextual matching when the
rule needs to know whether a row is falling under revenue / expense / capex /
other.

The file stores only exact learned rules from reviewed history:
- full `section_path`
- nearest section name
- top section name

If a row does not match these exact learned rules at runtime, Stage 1 should
leave it unresolved and let the AI stage handle it later.

Usage:
    python pipeline/0_build_rulebook/build_section_side_support.py

Input:
    output_docs/<date>/0_build_rulebook/reviewed_row_history/reviewed_row_history_index.json

Output:
    output_docs/<date>/0_build_rulebook/section_side_support/section_side_support.json
"""

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import REPO_ROOT, REVIEWED_ROW_HISTORY_INDEX_PATH, SECTION_SIDE_SUPPORT_PATH
from config.rulebook_utils import build_section_path_key, normalize_section_key


def build_rule_entry(name, counter: Counter) -> dict:
    if not counter:
        raise ValueError(f"Cannot build support entry with empty counts for '{name}'")

    if len(counter) != 1:
        raise ValueError(f"Support rule for '{name}' is ambiguous and should not become a direct rule")

    statement_side = next(iter(counter.keys()))
    occurrence_count = sum(counter.values())

    return {
        "statement_side": statement_side,
        "occurrence_count": occurrence_count,
        "counts": dict(sorted(counter.items())),
    }


if __name__ == "__main__":
    if not REVIEWED_ROW_HISTORY_INDEX_PATH.exists():
        raise FileNotFoundError(f"Reviewed-row history index not found: {REVIEWED_ROW_HISTORY_INDEX_PATH}")

    with open(REVIEWED_ROW_HISTORY_INDEX_PATH, "r") as f:
        history_index = json.load(f)

    by_path = defaultdict(Counter)
    by_nearest_section = defaultdict(Counter)
    by_top_section = defaultdict(Counter)
    display_path = {}
    display_nearest = {}
    display_top = {}

    for entry in history_index["descriptions"].values():
        for occ in entry["occurrences"]:
            side = occ.get("statement_side")
            if not side:
                continue

            path = occ.get("section_path") or []
            if path:
                path_lookup = build_section_path_key(path)
                if path_lookup:
                    by_path[path_lookup][side] += 1
                    display_path[path_lookup] = path

                top_section = path[0]
                top_lookup = normalize_section_key(top_section)
                if top_lookup:
                    by_top_section[top_lookup][side] += 1
                    display_top[top_lookup] = top_section

            nearest_section = occ.get("nearest_section")
            if nearest_section:
                nearest_lookup = normalize_section_key(nearest_section)
                by_nearest_section[nearest_lookup][side] += 1
                display_nearest[nearest_lookup] = nearest_section

    section_path_rules = {}
    ambiguous_section_paths = {}
    for lookup_key, counter in sorted(by_path.items()):
        if len(counter) == 1:
            entry = build_rule_entry(lookup_key, counter)
            entry["section_path"] = display_path[lookup_key]
            section_path_rules[lookup_key] = entry
        else:
            ambiguous_section_paths[lookup_key] = {
                "section_path": display_path[lookup_key],
                "counts": dict(sorted(counter.items())),
                "occurrence_count": sum(counter.values()),
            }

    nearest_section_rules = {}
    ambiguous_nearest_sections = {}
    for lookup_key, counter in sorted(by_nearest_section.items()):
        if len(counter) == 1:
            entry = build_rule_entry(lookup_key, counter)
            entry["nearest_section"] = display_nearest[lookup_key]
            nearest_section_rules[lookup_key] = entry
        else:
            ambiguous_nearest_sections[lookup_key] = {
                "nearest_section": display_nearest[lookup_key],
                "counts": dict(sorted(counter.items())),
                "occurrence_count": sum(counter.values()),
            }

    top_section_rules = {}
    ambiguous_top_sections = {}
    for lookup_key, counter in sorted(by_top_section.items()):
        if len(counter) == 1:
            entry = build_rule_entry(lookup_key, counter)
            entry["top_section"] = display_top[lookup_key]
            top_section_rules[lookup_key] = entry
        else:
            ambiguous_top_sections[lookup_key] = {
                "top_section": display_top[lookup_key],
                "counts": dict(sorted(counter.items())),
                "occurrence_count": sum(counter.values()),
            }

    payload = {
        "schema_version": "v3_section_side_support",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": str(REVIEWED_ROW_HISTORY_INDEX_PATH.relative_to(REPO_ROOT)),
        "summary": {
            "section_path_rules": len(section_path_rules),
            "ambiguous_section_paths": len(ambiguous_section_paths),
            "nearest_section_rules": len(nearest_section_rules),
            "ambiguous_nearest_sections": len(ambiguous_nearest_sections),
            "top_section_rules": len(top_section_rules),
            "ambiguous_top_sections": len(ambiguous_top_sections),
        },
        "section_path_rules": section_path_rules,
        "ambiguous_section_paths": ambiguous_section_paths,
        "nearest_section_rules": nearest_section_rules,
        "ambiguous_nearest_sections": ambiguous_nearest_sections,
        "top_section_rules": top_section_rules,
        "ambiguous_top_sections": ambiguous_top_sections,
    }

    with open(SECTION_SIDE_SUPPORT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    print("Built section-side support")
    print(f"  Section-path rules:      {len(section_path_rules)}")
    print(f"  Ambiguous section-paths: {len(ambiguous_section_paths)}")
    print(f"  Nearest-section rules:   {len(nearest_section_rules)}")
    print(f"  Ambiguous nearest:       {len(ambiguous_nearest_sections)}")
    print(f"  Top-section rules:       {len(top_section_rules)}")
    print(f"  Ambiguous top-sections:  {len(ambiguous_top_sections)}")
    print(f"Saved: {SECTION_SIDE_SUPPORT_PATH}")
