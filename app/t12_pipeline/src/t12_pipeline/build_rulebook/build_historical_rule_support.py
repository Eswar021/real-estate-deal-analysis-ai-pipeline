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
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from t12_pipeline.config.paths import (
    AUTO_ASSIGNED_CONFLICTS_PATH,
    AUTO_ASSIGNED_CONFLICTS_XLSX,
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


# Styling — matches conflict_sources_report_v2 exactly
_HEADER_FILL = PatternFill(start_color="FF1F4E79", end_color="FF1F4E79", fill_type="solid")
_HEADER_FONT = Font(bold=True, color="FFFFFFFF")
_HEADER_FONT_NOTES = Font(bold=True, color="FFFF0000")  # NOTES column has red text
_GROUP_FILL_WHITE = PatternFill(start_color="FFFFFFFF", end_color="FFFFFFFF", fill_type="solid")
_GROUP_FILL_BLUE = PatternFill(start_color="FFEBF3FB", end_color="FFEBF3FB", fill_type="solid")
_DESC_FONT = Font(bold=True)
_WRAP = Alignment(wrap_text=True, vertical="top")

# Thin grid border applied to every cell so groups read clearly.
_THIN = Side(border_style="thin", color="FFBFBFBF")
_CELL_BORDER = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)
# Slightly darker bottom on the last row of each description group — group separator.
_GROUP_SEP = Side(border_style="medium", color="FF808080")


def _apply_header(ws, headers: list[str], notes_col: int | None = None) -> None:
    """Write the header row with dark-blue fill + white font; NOTES column gets red font."""
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT_NOTES if (notes_col and col_idx == notes_col) else _HEADER_FONT
        cell.alignment = _WRAP
        cell.border = _CELL_BORDER


def _files_for_mapping(conflict: dict, candidate: str) -> list[str]:
    """Files whose final_mapping equals this candidate. Same data the rulebook used."""
    occurrences = conflict.get("occurrences") or []
    return sorted({
        occ["file"] for occ in occurrences
        if occ.get("final_mapping") == candidate and occ.get("file")
    })


def _files_for_mapping_and_side(conflict: dict, candidate: str, side: str) -> list[str]:
    """Files whose final_mapping AND statement_side match. Used for Revenue vs Expense rows."""
    occurrences = conflict.get("occurrences") or []
    return sorted({
        occ["file"] for occ in occurrences
        if occ.get("final_mapping") == candidate
        and occ.get("statement_side") == side
        and occ.get("file")
    })


def _style_group(ws, start_row: int, end_row: int, ncols: int, fill: PatternFill) -> None:
    """Apply zebra-stripe fill + wrap + bold-description-on-first-row + grid borders to a group."""
    for row_idx in range(start_row, end_row + 1):
        for col_idx in range(1, ncols + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = fill
            cell.alignment = _WRAP
            cell.border = _CELL_BORDER
            if col_idx == 1 and row_idx == start_row:
                cell.font = _DESC_FONT

    # Slightly heavier bottom border on the last row of the group — separates
    # one description from the next visually.
    for col_idx in range(1, ncols + 1):
        cell = ws.cell(row=end_row, column=col_idx)
        cell.border = Border(
            top=_THIN, bottom=_GROUP_SEP, left=_THIN, right=_THIN,
        )


def write_auto_assigned_xlsx(auto_assigned_keys: list[str], conflicts: dict, out_path: Path) -> None:
    """
    Write auto-routed conflicts in the same Excel format as the client conflict
    review workbook (conflict_sources_report_v2). Matches its visual styling
    so rows paste straight into the master workbook without reformatting.

    Two sheets:
      'Category Conflicts' (Row Description | Category | Source Files | NOTES)
          One row per (description × candidate mapping). Source Files lists
          only the files where the row's specific mapping was the final
          decision — not every file the description appeared in.

      'Revenue vs Expense' (Row Description | Category | Bucket | Source Files)
          Cross-side conflicts only (description seen as both revenue AND
          expense). One row per (mapping × statement_side) combination.

    Header: dark-blue (#1F4E79) fill + white font; NOTES header in red.
    Groups: alternate white / light-blue (#EBF3FB) zebra stripes.
    Description column: bold only on the first row of each group; blank otherwise.
    """
    wb = openpyxl.Workbook()

    # ── Sheet 1: Category Conflicts ───────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Category Conflicts"
    _apply_header(ws1, ["Row Description", "Category", "Source Files", "NOTES"], notes_col=4)

    use_blue = False
    for key in auto_assigned_keys:
        conflict = conflicts[key]
        candidates = conflict.get("mappings") or []
        if not candidates:
            continue
        group_start = ws1.max_row + 1
        for i, candidate in enumerate(candidates):
            files = _files_for_mapping(conflict, candidate)
            ws1.append([
                key if i == 0 else None,
                candidate,
                "\n".join(files) if files else "",
                None,
            ])
        _style_group(ws1, group_start, ws1.max_row, 4,
                     _GROUP_FILL_BLUE if use_blue else _GROUP_FILL_WHITE)
        use_blue = not use_blue

    # ── Sheet 2: Revenue vs Expense (cross-side conflicts only) ──────────────
    ws2 = wb.create_sheet("Revenue vs Expense")
    _apply_header(ws2, ["Row Description", "Category", "Bucket", "Source Files"])

    use_blue = False
    for key in auto_assigned_keys:
        conflict = conflicts[key]
        sides = set(conflict.get("statement_sides") or [])
        if not {"revenue", "expense"}.issubset(sides):
            continue

        # Build unique (mapping, side) combinations from occurrences
        seen = set()
        combos = []
        for occ in conflict.get("occurrences") or []:
            fm = occ.get("final_mapping")
            ss = occ.get("statement_side")
            if fm and ss in ("revenue", "expense") and (fm, ss) not in seen:
                seen.add((fm, ss))
                combos.append((fm, ss))
        # Stable sort: expense rows first, then revenue, alphabetical within each
        combos.sort(key=lambda x: (x[1] != "expense", x[0]))

        if not combos:
            continue

        group_start = ws2.max_row + 1
        for i, (candidate, side) in enumerate(combos):
            files = _files_for_mapping_and_side(conflict, candidate, side)
            ws2.append([
                key if i == 0 else None,
                candidate,
                side.upper(),
                "\n".join(files) if files else "",
            ])
        _style_group(ws2, group_start, ws2.max_row, 4,
                     _GROUP_FILL_BLUE if use_blue else _GROUP_FILL_WHITE)
        use_blue = not use_blue

    # Column widths matching the reference workbook
    for ws in (ws1, ws2):
        ws.column_dimensions["A"].width = 40
        ws.column_dimensions["B"].width = 30
        ws.column_dimensions["C"].width = 60
        ws.column_dimensions["D"].width = 50
        ws.freeze_panes = "A2"  # keep header visible while scrolling

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


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
    auto_assigned_keys: list[str] = []

    review_bucket_counts = {
        "certain": 0,
        "contextual": 0,
        "unresolved": 0,
        "not_in_review": 0,  # informational: how many of "unresolved" were auto-routed
    }

    for key, entry in sorted(history_descriptions.items()):
        mapping_count = len(entry["mappings"])

        if mapping_count == 1:
            no_conflict[key] = build_no_conflict_entry(entry)
            continue

        client_review_info = client_review_lookup.get(key)

        if client_review_info is None:
            # Auto-route: conflict description isn't in the client review workbook yet.
            # Treat it as 'unresolved' so the build can proceed; AI fallback will handle
            # it at runtime. Track the key so we write a list for the client to review.
            client_review_info = {
                "bucket": "unresolved",
                "entry": {
                    "auto_assigned": True,
                    "reason": "not in client conflict review workbook — auto-routed to unresolved",
                    "candidate_mappings": entry["mappings"],
                },
            }
            auto_assigned_keys.append(key)
            review_bucket_counts["not_in_review"] += 1

        conflicts[key] = build_conflict_entry(entry, client_review_info)
        review_bucket_counts[client_review_info["bucket"]] += 1

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

    NO_CONFLICT_RULEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(NO_CONFLICT_RULEBOOK_PATH, "w") as f:
        json.dump(no_conflict_payload, f, indent=2)

    with open(HISTORICAL_CONFLICTS_PATH, "w") as f:
        json.dump(historical_conflicts_payload, f, indent=2)

    auto_assigned_payload = {
        "schema_version": "v3_auto_assigned",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "note": (
            "These conflict descriptions were found in the .xlsm history with multiple "
            "mappings but are NOT in the client conflict review workbook "
            "(conflict_sources_report). They were auto-routed to 'unresolved' so the "
            "build wouldn't fail; AI fallback handles them at runtime. The client "
            "should review each one and explicitly categorize it as certain / "
            "contextual / unresolved in the conflict review workbook."
        ),
        "summary": {"total_auto_assigned": len(auto_assigned_keys)},
        "auto_assigned": [
            {
                "description": key,
                "candidate_mappings": conflicts[key]["mappings"],
                "statement_sides": conflicts[key]["statement_sides"],
                "occurrence_count": conflicts[key]["occurrence_count"],
                "files_seen": conflicts[key]["files_seen"],
            }
            for key in auto_assigned_keys
        ],
    }

    with open(AUTO_ASSIGNED_CONFLICTS_PATH, "w") as f:
        json.dump(auto_assigned_payload, f, indent=2)

    # Write the same data in the client's conflict workbook format (.xlsx)
    # so the client can paste rows straight into conflict_sources_report.
    write_auto_assigned_xlsx(auto_assigned_keys, conflicts, AUTO_ASSIGNED_CONFLICTS_XLSX)

    print("Built historical rule support")
    print(f"  No-conflict descriptions:   {len(no_conflict)}")
    print(f"  Conflict descriptions:      {len(conflicts)}")
    print(f"  Review bucket counts:       {review_bucket_counts}")
    if auto_assigned_keys:
        print(
            f"  ⚠ {len(auto_assigned_keys)} conflict(s) auto-routed to 'unresolved' "
            f"(client should review):"
        )
        for key in auto_assigned_keys:
            print(f"      • {key}")
    print(f"Saved: {NO_CONFLICT_RULEBOOK_PATH}")
    print(f"Saved: {HISTORICAL_CONFLICTS_PATH}")
    print(f"Saved: {AUTO_ASSIGNED_CONFLICTS_PATH}")
    print(f"Saved: {AUTO_ASSIGNED_CONFLICTS_XLSX}  ← send this to the client")
