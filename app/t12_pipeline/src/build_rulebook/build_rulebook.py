"""
build_rulebook.py

Builds the current mapping rulebook from the already-prepared support layers:

1. client-reviewed decisions
2. historical no_conflict output
3. historical conflicts support

The runtime rulebook keeps four sections:
- certain
- contextual
- no_conflict
- unresolved

Usage:
    python src/build_rulebook/build_rulebook.py

Input:
    output_docs/<timestamp>/build_rulebook/client_review_rules/client_review_rulebook_phase1.json
    output_docs/<timestamp>/build_rulebook/historical_rule_support/no_conflict_rulebook.json
    output_docs/<timestamp>/build_rulebook/historical_rule_support/historical_conflicts.json

Output:
    db/rulebooks/mapping_rulebook_<timestamp>.json
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.paths import (
    CLIENT_REVIEW_RULES_PATH,
    HISTORICAL_CONFLICTS_PATH,
    NO_CONFLICT_RULEBOOK_PATH,
    REPO_ROOT,
    RULEBOOK_DB_OUTPUT_PATH,
)


CLIENT_REVIEW_BUCKETS = ("certain", "contextual", "unresolved")


def load_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def validate_required_files() -> None:
    required = [
        CLIENT_REVIEW_RULES_PATH,
        NO_CONFLICT_RULEBOOK_PATH,
        HISTORICAL_CONFLICTS_PATH,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input file(s): " + ", ".join(missing))


def ensure_same_source_date(payloads: list[tuple[str, dict]]) -> None:
    source_files = []
    for label, payload in payloads:
        files = payload.get("source_files", {})
        source_files.append((label, files))

    historical_files = dict(source_files[1][1])
    conflict_files = dict(source_files[2][1])
    if historical_files != conflict_files:
        raise ValueError("Historical support payload source files do not match")


def validate_no_overlap(*sections: tuple[str, dict]) -> None:
    seen: dict[str, str] = {}
    for section_name, entries in sections:
        for key in entries:
            if key in seen:
                raise ValueError(
                    f"Description key '{key}' appears in both '{seen[key]}' and '{section_name}'"
                )
            seen[key] = section_name


def validate_conflict_links(conflicts: dict) -> None:
    for key, entry in conflicts.items():
        bucket = entry.get("client_review_bucket")
        review_entry = entry.get("client_review_entry")
        if bucket not in CLIENT_REVIEW_BUCKETS:
            raise ValueError(f"Conflict entry '{key}' has invalid client_review_bucket: {bucket}")
        if not isinstance(review_entry, dict):
            raise ValueError(f"Conflict entry '{key}' is missing client_review_entry metadata")


if __name__ == "__main__":
    validate_required_files()

    client_review = load_json(CLIENT_REVIEW_RULES_PATH)
    no_conflict_payload = load_json(NO_CONFLICT_RULEBOOK_PATH)
    historical_conflicts_payload = load_json(HISTORICAL_CONFLICTS_PATH)

    ensure_same_source_date([
        ("client_review", client_review),
        ("no_conflict", no_conflict_payload),
        ("historical_conflicts", historical_conflicts_payload),
    ])

    certain = client_review["certain"]
    contextual = client_review["contextual"]
    unresolved = client_review["unresolved"]
    no_conflict = no_conflict_payload["no_conflict"]
    historical_conflicts = historical_conflicts_payload["conflicts"]

    validate_conflict_links(historical_conflicts)
    validate_no_overlap(
        ("certain", certain),
        ("contextual", contextual),
        ("no_conflict", no_conflict),
        ("unresolved", unresolved),
    )

    # Embed historical conflict context directly into unresolved entries so
    # Stage 1 only needs to read the single runtime rulebook file.
    for key, entry in unresolved.items():
        conflict = historical_conflicts.get(key, {})
        if conflict:
            entry["historical_candidate_mappings"] = conflict.get("mappings", [])
            entry["historical_statement_sides"] = conflict.get("statement_sides", [])
            entry["historical_section_paths"] = conflict.get("section_paths", [])

    total_runtime_descriptions = (
        len(certain) +
        len(contextual) +
        len(no_conflict) +
        len(unresolved)
    )

    expected_total = no_conflict_payload["summary"]["total_descriptions"]
    if total_runtime_descriptions != expected_total:
        raise ValueError(
            "Merged rulebook description count mismatch: "
            f"{total_runtime_descriptions} != {expected_total}"
        )

    for key in list(certain) + list(contextual) + list(unresolved):
        if key not in historical_conflicts:
            raise ValueError(f"Client-reviewed description missing from historical conflicts: {key}")

    no_conflict_cross_side = sum(
        1 for entry in no_conflict.values() if len(entry.get("statement_sides", [])) > 1
    )
    no_conflict_missing_side = sum(
        1 for entry in no_conflict.values() if len(entry.get("statement_sides", [])) == 0
    )

    merged_rulebook = {
        "schema_version": "runtime_rulebook",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": {
            "client_review_rules": str(CLIENT_REVIEW_RULES_PATH.relative_to(REPO_ROOT)),
            "no_conflict_rulebook": str(NO_CONFLICT_RULEBOOK_PATH.relative_to(REPO_ROOT)),
            "historical_conflicts": str(HISTORICAL_CONFLICTS_PATH.relative_to(REPO_ROOT)),
        },
        "summary": {
            "certain": len(certain),
            "contextual": len(contextual),
            "no_conflict": len(no_conflict),
            "unresolved": len(unresolved),
            "total_runtime_descriptions": total_runtime_descriptions,
            "no_conflict_cross_side": no_conflict_cross_side,
            "no_conflict_missing_side": no_conflict_missing_side,
        },
        "lookup_order": [
            "certain",
            "contextual",
            "no_conflict",
            "unresolved",
        ],
        "certain": certain,
        "contextual": contextual,
        "no_conflict": no_conflict,
        "unresolved": unresolved,
    }

    with open(RULEBOOK_DB_OUTPUT_PATH, "w") as f:
        json.dump(merged_rulebook, f, indent=2)

    print("Built runtime rulebook")
    print(f"  Certain:       {len(certain)}")
    print(f"  Contextual:    {len(contextual)}")
    print(f"  No-conflict:   {len(no_conflict)}")
    print(f"  Unresolved:    {len(unresolved)}")
    print(f"  Total:         {total_runtime_descriptions}")
    print(f"Saved: {RULEBOOK_DB_OUTPUT_PATH}")
