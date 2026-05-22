"""
build_client_review_rules.py

Phase 1 builder for the client-reviewed conflict workbook.

This script only reads the reviewed conflict Excel file and classifies each
reviewed row-description conflict into one of three sections:
  - certain
  - contextual
  - unresolved

It does NOT touch the 19 reviewed mapping xlsm files yet.
That later phase will build the no_conflict section separately.

Usage:
    python pipeline/0_build_rulebook/build_client_review_rules.py

Input:
    data/client_review_docs/
        conflict_sources_report_v2_J VM Notes.xlsx

Output:
    output_docs/<date>/0_build_rulebook/client_review_rules/
        client_review_rulebook_phase1.json
"""

import json
from datetime import datetime
from pathlib import Path

import openpyxl

from t12_pipeline.config.paths import CLIENT_REVIEW_CONFLICTS_FILE, CLIENT_REVIEW_RULES_PATH, REPO_ROOT


SELECTED_YELLOW = "FFFFFF00"


# Client-reviewed note groups that should become direct mappings.
CERTAIN_NOTE_MAPPINGS = {
    "Bad Debt Recovery Collections - Other Income": "Bad Debt",
    "Deposit Waiver Program": "Other Income Ops",
    "Ranges": "Turnover Expenses",
    "Renters Insurance": "Other Income: Value Add",
}


# Client-reviewed note groups that can be converted into explicit runtime rules.
CONTEXTUAL_STATEMENT_SIDE = {
    "Eviction Fees": {
        "expense": "Administrative",
        "revenue": "Other Income Ops",
    },
    "Locks And Keys": {
        "expense": "Repairs And Maintenance",
        "revenue": "Other Income Ops",
    },
    "Miscellaneous": {
        "expense": "Administrative",
        "revenue": "Other Income Ops",
    },
    "Pest Control": {
        "expense": "Contracted Services",
        "revenue": "Other Income: Value Add",
    },
    "Pest Control Treatment": {
        "expense": "Contracted Services",
        "revenue": "Other Income: Value Add",
    },
    "Trash": {
        "expense": "Contracted Services",
        "revenue": "Other Income: Value Add",
    },
    "Trash Collection": {
        "expense": "Contracted Services",
        "revenue": "Other Income: Value Add",
    },
    "Trash Removal": {
        "expense": "Contracted Services",
        "revenue": "Other Income: Value Add",
    },
    "Valet Trash": {
        "expense": "Contracted Services",
        "revenue": "Other Income: Value Add",
    },
}


CONTEXTUAL_SECTION_RULES = {
    "Grounds": {
        "default_mapping": "Contracted Services",
        "section_rules": [
            {
                "section_contains": "payroll",
                "mapping": "Payroll Salaries/Wages",
            }
        ],
    }
}


# Everything else with a client note stays unresolved for AI, but we keep the
# reason type so the runtime can pass stronger context to the AI prompt later.
UNRESOLVED_REASON_TYPES = {
    "Cable": "vague_context",
    "Cable Income": "vague_context",
    "Cable Income (Gaap)": "owner_specific",
    "Cam Fees": "buyer_specific",
    "Cleaning": "vague_context",
    "Cleaning Service": "vague_context",
    "Custodial": "vague_context",
    "Legal Fees": "vague_context",
    "Reserved/ Covered Parking Fees": "future_category",
    "Utility Billing": "future_category",
    "Utility Billing Fee": "future_category",
    "Utility Billing Fees": "future_category",
}


EXPECTED_NOTE_GROUPS = (
    set(CERTAIN_NOTE_MAPPINGS)
    | set(CONTEXTUAL_STATEMENT_SIDE)
    | set(CONTEXTUAL_SECTION_RULES)
    | set(UNRESOLVED_REASON_TYPES)
)


def normalize_key(text: str) -> str:
    return text.strip().lower()


def normalize_note(value) -> str | None:
    if not isinstance(value, str):
        return None
    note = value.strip()
    return note or None


def normalize_mapping(value) -> str | None:
    if not isinstance(value, str):
        return None
    mapping = value.strip()
    return mapping or None


def is_selected_category(cell) -> bool:
    fill = cell.fill
    if fill.fill_type != "solid":
        return False

    rgb = fill.fgColor.rgb
    if not isinstance(rgb, str):
        return False

    return rgb.upper() == SELECTED_YELLOW


def load_review_groups(workbook_path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(workbook_path)

    if "Category Conflicts" not in wb.sheetnames:
        wb.close()
        raise ValueError("Expected sheet 'Category Conflicts' not found")

    ws = wb["Category Conflicts"]
    expected_headers = ["Row Description", "Category", "Source Files", "NOTES"]
    actual_headers = [ws.cell(1, col).value for col in range(1, 5)]
    if actual_headers != expected_headers:
        wb.close()
        raise ValueError(
            f"Unexpected headers in reviewed workbook. Expected {expected_headers}, got {actual_headers}"
        )

    groups: list[dict] = []
    current_group = None

    for row_idx in range(2, ws.max_row + 1):
        desc_cell = ws.cell(row_idx, 1)
        cat_cell = ws.cell(row_idx, 2)
        note_cell = ws.cell(row_idx, 4)

        desc = desc_cell.value
        category = normalize_mapping(cat_cell.value)
        note = normalize_note(note_cell.value)

        if desc:
            if current_group:
                groups.append(current_group)
            current_group = {
                "row_description": str(desc).strip(),
                "reviewed_categories": [],
                "selected_categories": [],
                "review_notes": [],
            }

        if current_group is None:
            wb.close()
            raise ValueError(f"Row {row_idx} appears before any row description group starts")

        if category:
            current_group["reviewed_categories"].append(category)
            if is_selected_category(cat_cell):
                current_group["selected_categories"].append(category)

        if note:
            current_group["review_notes"].append(note)

    if current_group:
        groups.append(current_group)

    wb.close()
    return groups


def build_certain_entry(group: dict, mapping: str) -> dict:
    notes = group["review_notes"]
    return {
        "row_description": group["row_description"],
        "mapping": mapping,
        "review_note": notes[0] if notes else None,
    }


def build_contextual_entry(group: dict) -> dict:
    desc = group["row_description"]
    notes = group["review_notes"]

    if desc in CONTEXTUAL_STATEMENT_SIDE:
        return {
            "row_description": desc,
            "rule_type": "statement_side",
            "conditions": CONTEXTUAL_STATEMENT_SIDE[desc],
            "review_note": notes[0],
        }

    if desc in CONTEXTUAL_SECTION_RULES:
        rule = CONTEXTUAL_SECTION_RULES[desc]
        return {
            "row_description": desc,
            "rule_type": "section_rule",
            "default_mapping": rule["default_mapping"],
            "section_rules": rule["section_rules"],
            "review_note": notes[0],
        }

    raise ValueError(f"No contextual rule builder defined for '{desc}'")


def build_unresolved_entry(group: dict) -> dict:
    desc = group["row_description"]
    notes = group["review_notes"]

    return {
        "row_description": desc,
        "reason_type": UNRESOLVED_REASON_TYPES[desc],
        "review_note": notes[0],
    }


def classify_groups(groups: list[dict]) -> dict:
    note_groups_seen = set()

    rulebook = {
        "schema_version": "v3_review_phase_1",
        "source_file": str(CLIENT_REVIEW_CONFLICTS_FILE.relative_to(REPO_ROOT)),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "reviewed_conflict_groups": len(groups),
            "certain": 0,
            "contextual": 0,
            "unresolved": 0,
        },
        "certain": {},
        "contextual": {},
        "unresolved": {},
    }

    for group in groups:
        desc = group["row_description"]
        key = normalize_key(desc)
        selected = group["selected_categories"]
        notes = group["review_notes"]

        if len(selected) > 1:
            raise ValueError(f"Multiple highlighted categories found for '{desc}': {selected}")

        if notes:
            note_groups_seen.add(desc)

            if desc in CERTAIN_NOTE_MAPPINGS:
                entry = build_certain_entry(group, CERTAIN_NOTE_MAPPINGS[desc])
                rulebook["certain"][key] = entry
                rulebook["summary"]["certain"] += 1
                continue

            if desc in CONTEXTUAL_STATEMENT_SIDE or desc in CONTEXTUAL_SECTION_RULES:
                entry = build_contextual_entry(group)
                rulebook["contextual"][key] = entry
                rulebook["summary"]["contextual"] += 1
                continue

            if desc in UNRESOLVED_REASON_TYPES:
                entry = build_unresolved_entry(group)
                rulebook["unresolved"][key] = entry
                rulebook["summary"]["unresolved"] += 1
                continue

            raise ValueError(
                f"Client note group '{desc}' is not classified in the phase-1 decision tables"
            )

        if len(selected) != 1:
            raise ValueError(
                f"Expected exactly one highlighted category for note-free group '{desc}', got {selected}"
            )

        entry = build_certain_entry(group, selected[0])
        rulebook["certain"][key] = entry
        rulebook["summary"]["certain"] += 1

    unexpected_note_groups = note_groups_seen - EXPECTED_NOTE_GROUPS
    missing_note_groups = EXPECTED_NOTE_GROUPS - note_groups_seen

    if unexpected_note_groups:
        raise ValueError(f"Unexpected note groups found: {sorted(unexpected_note_groups)}")
    if missing_note_groups:
        raise ValueError(f"Expected note groups missing: {sorted(missing_note_groups)}")

    total_classified = (
        rulebook["summary"]["certain"]
        + rulebook["summary"]["contextual"]
        + rulebook["summary"]["unresolved"]
    )

    if total_classified != len(groups):
        raise ValueError(
            f"Classification count mismatch: grouped={len(groups)}, classified={total_classified}"
        )

    return rulebook


def main() -> None:
    if not CLIENT_REVIEW_CONFLICTS_FILE.exists():
        raise FileNotFoundError(f"Client review workbook not found: {CLIENT_REVIEW_CONFLICTS_FILE}")

    groups = load_review_groups(CLIENT_REVIEW_CONFLICTS_FILE)
    rulebook = classify_groups(groups)

    with open(CLIENT_REVIEW_RULES_PATH, "w") as f:
        json.dump(rulebook, f, indent=2)

    summary = rulebook["summary"]
    print(f"Built client review phase-1 rules from: {CLIENT_REVIEW_CONFLICTS_FILE.name}")
    print(f"  Reviewed conflict groups: {summary['reviewed_conflict_groups']}")
    print(f"  Certain:                 {summary['certain']}")
    print(f"  Contextual:              {summary['contextual']}")
    print(f"  Unresolved:              {summary['unresolved']}")
    print(f"Saved: {CLIENT_REVIEW_RULES_PATH}")


if __name__ == "__main__":
    main()
