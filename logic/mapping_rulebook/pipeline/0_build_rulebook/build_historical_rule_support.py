"""
build_historical_rule_support.py

Support builder for the historical rulebook layer.

This script reads:
  1. the phase-1 client-reviewed decisions
  2. the reviewed `.xlsm` history index

and splits the historical extraction into two output files:
  - no_conflict_rulebook.json
  - historical_conflicts.json

The goal is to keep this phase separate from the client-review phase:
  - client review decides certain / contextual / unresolved
  - historical extraction supplies no_conflict and conflict-support context

Usage:
    python pipeline/0_build_rulebook/build_historical_rule_support.py

Input:
    output_docs/<date>/0_build_rulebook/client_review_rules/client_review_rulebook_phase1.json
    output_docs/<date>/0_build_rulebook/reviewed_row_history/reviewed_row_history_index.json

Output:
    output_docs/<date>/0_build_rulebook/historical_rule_support/no_conflict_rulebook.json
    output_docs/<date>/0_build_rulebook/historical_rule_support/historical_conflicts.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    CLIENT_REVIEW_RULES_PATH,
    HISTORICAL_CONFLICTS_PATH,
    NO_CONFLICT_RULEBOOK_PATH,
    REVIEWED_ROW_HISTORY_INDEX_PATH,
    REPO_ROOT,
)


CLIENT_REVIEW_BUCKETS = ("certain", "contextual", "unresolved")


def load_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def build_client_review_lookup(client_review_rules: dict) -> dict[str, dict]:
    lookup: dict[str, dict] = {}

    for bucket in CLIENT_REVIEW_BUCKETS:
        entries = client_review_rules.get(bucket, {})
        for key, value in entries.items():
            if key in lookup:
                raise ValueError(f"Duplicate client review key across buckets: {key}")

            lookup[key] = {
                "bucket": bucket,
                "entry": value,
            }

    return lookup


def validate_client_review_against_history(client_review_lookup: dict[str, dict], history_descriptions: dict) -> None:
    missing = sorted(key for key in client_review_lookup if key not in history_descriptions)
    if missing:
        preview = ", ".join(missing[:10])
        raise ValueError(
            "Some client-reviewed descriptions were not found in the reviewed-row history index: "
            f"{preview}"
        )

    wrong_shape = sorted(
        key
        for key, info in client_review_lookup.items()
        if len(history_descriptions[key]["mappings"]) <= 1
    )
    if wrong_shape:
        preview = ", ".join(wrong_shape[:10])
        raise ValueError(
            "Some client-reviewed descriptions are not historical conflicts in the reviewed-row history index: "
            f"{preview}"
        )


def build_no_conflict_entry(entry: dict) -> dict:
    mappings = entry["mappings"]
    if len(mappings) != 1:
        raise ValueError(f"Expected exactly one mapping for no_conflict entry: {entry['row_description']}")

    return {
        "row_description": entry["row_description"],
        "mapping": mappings[0],
        "statement_sides": entry["statement_sides"],
        "nearest_sections": entry["nearest_sections"],
        "section_paths": entry["section_paths"],
        "files_seen": entry["files_seen"],
        "occurrence_count": entry["occurrence_count"],
    }


def build_conflict_entry(entry: dict, client_review_info: dict | None) -> dict:
    conflict_entry = {
        "row_description": entry["row_description"],
        "mappings": entry["mappings"],
        "statement_sides": entry["statement_sides"],
        "nearest_sections": entry["nearest_sections"],
        "section_paths": entry["section_paths"],
        "files_seen": entry["files_seen"],
        "occurrence_count": entry["occurrence_count"],
        "occurrences": entry["occurrences"],
        "client_review_bucket": None,
        "client_review_entry": None,
    }

    if client_review_info:
        conflict_entry["client_review_bucket"] = client_review_info["bucket"]
        conflict_entry["client_review_entry"] = client_review_info["entry"]

    return conflict_entry


if __name__ == "__main__":
    if not CLIENT_REVIEW_RULES_PATH.exists():
        raise FileNotFoundError(f"Client review rules not found: {CLIENT_REVIEW_RULES_PATH}")

    if not REVIEWED_ROW_HISTORY_INDEX_PATH.exists():
        raise FileNotFoundError(f"Reviewed-row history index not found: {REVIEWED_ROW_HISTORY_INDEX_PATH}")

    client_review_rules = load_json(CLIENT_REVIEW_RULES_PATH)
    reviewed_history = load_json(REVIEWED_ROW_HISTORY_INDEX_PATH)

    history_descriptions = reviewed_history["descriptions"]
    client_review_lookup = build_client_review_lookup(client_review_rules)
    validate_client_review_against_history(client_review_lookup, history_descriptions)

    no_conflict = {}
    conflicts = {}

    review_bucket_counts = {
        "certain": 0,
        "contextual": 0,
        "unresolved": 0,
        "not_in_review": 0,
    }

    for key, entry in sorted(history_descriptions.items()):
        mapping_count = len(entry["mappings"])

        if mapping_count == 1:
            no_conflict[key] = build_no_conflict_entry(entry)
            continue

        client_review_info = client_review_lookup.get(key)
        conflicts[key] = build_conflict_entry(entry, client_review_info)

        if client_review_info:
            review_bucket_counts[client_review_info["bucket"]] += 1
        else:
            review_bucket_counts["not_in_review"] += 1

    no_conflict_payload = {
        "schema_version": "v3_historical_support",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": {
            "client_review_rules": str(CLIENT_REVIEW_RULES_PATH.relative_to(REPO_ROOT)),
            "reviewed_row_history_index": str(REVIEWED_ROW_HISTORY_INDEX_PATH.relative_to(REPO_ROOT)),
        },
        "summary": {
            "total_descriptions": len(history_descriptions),
            "no_conflict_descriptions": len(no_conflict),
            "client_review_descriptions": len(client_review_lookup),
        },
        "no_conflict": no_conflict,
    }

    historical_conflicts_payload = {
        "schema_version": "v3_historical_support",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": {
            "client_review_rules": str(CLIENT_REVIEW_RULES_PATH.relative_to(REPO_ROOT)),
            "reviewed_row_history_index": str(REVIEWED_ROW_HISTORY_INDEX_PATH.relative_to(REPO_ROOT)),
        },
        "summary": {
            "total_conflict_descriptions": len(conflicts),
            "review_bucket_counts": review_bucket_counts,
        },
        "conflicts": conflicts,
    }

    with open(NO_CONFLICT_RULEBOOK_PATH, "w") as f:
        json.dump(no_conflict_payload, f, indent=2)

    with open(HISTORICAL_CONFLICTS_PATH, "w") as f:
        json.dump(historical_conflicts_payload, f, indent=2)

    print("Built historical rule support")
    print(f"  No-conflict descriptions:   {len(no_conflict)}")
    print(f"  Conflict descriptions:      {len(conflicts)}")
    print(f"  Review bucket counts:       {review_bucket_counts}")
    print(f"Saved: {NO_CONFLICT_RULEBOOK_PATH}")
    print(f"Saved: {HISTORICAL_CONFLICTS_PATH}")
