"""
extract_reviewed_row_history.py

Support builder for the later no_conflict / historical-conflict phase.

This script reads all 19 human-reviewed `.xlsm` mapping files and extracts
enriched history for every mapped data row. The goal is to preserve more context
than the current v2 extractor, especially:
  - statement side (revenue / expense)
  - the visible header chain above the row (`section_path`)
  - auto mapping / override / final mapping

This script does NOT build the final runtime rulebook yet.
It does NOT read the client-reviewed conflict workbook.
It only creates historical extraction artifacts from the reviewed `.xlsm` files.

Usage:
    python pipeline/0_build_rulebook/extract_reviewed_row_history.py

Input:
    data/mapped_T12_docs/t12_docs/*.xlsm
    data/mapped_T12_docs/new_t12_docs/*.xlsm

Output:
    output_docs/<date>/0_build_rulebook/reviewed_row_history/per_file/<filename>.json
    output_docs/<date>/0_build_rulebook/reviewed_row_history/reviewed_row_history_index.json
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.paths import (
    MAPPED_T12_DOCS_DIR,
    NEW_MAPPED_T12_DOCS_DIR,
    REPO_ROOT,
    REVIEWED_ROW_HISTORY_INDEX_PATH,
    REVIEWED_ROW_HISTORY_PER_FILE_DIR,
)


REQUIRED_COLS = [
    "Row Description (from T12)",
    "Auto Mapping",
    "OVERRIDE",
    "Final_Mapping",
]

OPTIONAL_COLS = [
    "Row",
    "income_exp_mapped",
    "+/- Sign",
]

STRUCTURAL_MARKERS = {
    "Likely Header": "header",
    "Likely Subtotal": "subtotal",
}


def normalize_text(value):
    """Normalize strings for consistent comparison and JSON output."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped.title() if stripped else None


def normalize_key(value: str) -> str:
    return value.strip().lower()


def normalize_statement_side(value):
    normalized = normalize_text(value)
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered == "income":
        return "revenue"
    if lowered == "expense":
        return "expense"
    return lowered


def find_anchor_row(ws):
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and isinstance(cell.value, str) and "COMPLETE MAPPING HERE" in cell.value.upper():
                return cell.row
    return None


def build_col_index(headers):
    col_idx = {}
    for col_name in REQUIRED_COLS:
        try:
            col_idx[col_name] = headers.index(col_name)
        except ValueError:
            raise ValueError(f"Required column '{col_name}' not found in header row")

    for col_name in OPTIONAL_COLS:
        try:
            col_idx[col_name] = headers.index(col_name)
        except ValueError:
            col_idx[col_name] = None

    return col_idx


def get_cell_value(row, index):
    if index is None:
        return None
    if index >= len(row):
        return None
    return row[index]


def load_table_rows(file_path: Path):
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)

    if "Financials" not in wb.sheetnames:
        wb.close()
        raise ValueError("No 'Financials' sheet found")

    ws = wb["Financials"]
    anchor_row = find_anchor_row(ws)
    if not anchor_row:
        wb.close()
        raise ValueError("Anchor row ('COMPLETE MAPPING HERE') not found")

    raw_rows = list(ws.iter_rows(min_row=anchor_row + 1, values_only=True))
    wb.close()

    if not raw_rows:
        raise ValueError("No data rows below anchor row")

    all_rows = [raw_rows[0]]
    for data_row in raw_rows[1:]:
        if not data_row or data_row[0] is None:
            break
        all_rows.append(data_row)

    return anchor_row, all_rows


def extract_file(file_path: Path):
    anchor_row, all_rows = load_table_rows(file_path)
    headers = all_rows[0]
    col_idx = build_col_index(headers)

    current_section_headers: list[str] = []
    extracted_rows = []
    structural_counts = {"header": 0, "subtotal": 0, "blank": 0}

    for offset, data_row in enumerate(all_rows[1:], start=1):
        sheet_row = anchor_row + offset + 1

        row_description = normalize_text(get_cell_value(data_row, col_idx["Row Description (from T12)"]))
        auto_mapping = normalize_text(get_cell_value(data_row, col_idx["Auto Mapping"]))
        override = normalize_text(get_cell_value(data_row, col_idx["OVERRIDE"]))
        final_mapping = normalize_text(get_cell_value(data_row, col_idx["Final_Mapping"]))
        statement_side = normalize_statement_side(get_cell_value(data_row, col_idx["income_exp_mapped"]))
        plus_minus_sign = get_cell_value(data_row, col_idx["+/- Sign"])
        source_row_number = get_cell_value(data_row, col_idx["Row"])

        if not row_description and not auto_mapping and not override and not final_mapping:
            structural_counts["blank"] += 1
            current_section_headers = []
            continue

        structural_kind = STRUCTURAL_MARKERS.get(auto_mapping)
        if structural_kind == "header":
            if not row_description:
                raise ValueError(f"Header row missing description in {file_path.name} at sheet row {sheet_row}")
            structural_counts["header"] += 1
            current_section_headers.append(row_description)
            continue

        if structural_kind == "subtotal":
            structural_counts["subtotal"] += 1
            current_section_headers = []
            continue

        if not row_description or not final_mapping:
            continue

        source_type = "override" if override else "auto"

        extracted_rows.append({
            "file": file_path.name,
            "sheet_row": sheet_row,
            "source_row_number": source_row_number,
            "row_description": row_description,
            "row_description_key": normalize_key(row_description),
            "statement_side": statement_side,
            "section_path": list(current_section_headers),
            "nearest_section": current_section_headers[-1] if current_section_headers else None,
            "auto_mapping": auto_mapping,
            "override": override,
            "final_mapping": final_mapping,
            "source_type": source_type,
            "plus_minus_sign": plus_minus_sign,
        })

    return {
        "file": file_path.name,
        "source_file": str(file_path.relative_to(REPO_ROOT)),
        "total_rows": len(extracted_rows),
        "override_rows": sum(1 for row in extracted_rows if row["source_type"] == "override"),
        "auto_rows": sum(1 for row in extracted_rows if row["source_type"] == "auto"),
        "unique_row_descriptions": len({row["row_description_key"] for row in extracted_rows}),
        "structural_rows": structural_counts,
        "rows": extracted_rows,
    }


def build_history_index(per_file_results):
    descriptions = defaultdict(list)

    for result in per_file_results:
        for row in result["rows"]:
            descriptions[row["row_description_key"]].append({
                "row_description": row["row_description"],
                "file": row["file"],
                "sheet_row": row["sheet_row"],
                "source_row_number": row["source_row_number"],
                "statement_side": row["statement_side"],
                "section_path": row["section_path"],
                "nearest_section": row["nearest_section"],
                "auto_mapping": row["auto_mapping"],
                "override": row["override"],
                "final_mapping": row["final_mapping"],
                "source_type": row["source_type"],
                "plus_minus_sign": row["plus_minus_sign"],
            })

    description_entries = {}
    single_mapping_count = 0
    multi_mapping_count = 0
    cross_statement_side_count = 0

    for key, occurrences in sorted(descriptions.items()):
        mappings = sorted({occ["final_mapping"] for occ in occurrences if occ["final_mapping"]})
        statement_sides = sorted({occ["statement_side"] for occ in occurrences if occ["statement_side"]})
        nearest_sections = sorted({occ["nearest_section"] for occ in occurrences if occ["nearest_section"]})
        section_paths = sorted({
            " > ".join(occ["section_path"])
            for occ in occurrences
            if occ["section_path"]
        })

        if len(mappings) == 1:
            single_mapping_count += 1
        else:
            multi_mapping_count += 1

        if len(statement_sides) > 1:
            cross_statement_side_count += 1

        description_entries[key] = {
            "row_description": occurrences[0]["row_description"],
            "files_seen": len({occ["file"] for occ in occurrences}),
            "occurrence_count": len(occurrences),
            "mappings": mappings,
            "statement_sides": statement_sides,
            "nearest_sections": nearest_sections,
            "section_paths": section_paths,
            "occurrences": occurrences,
        }

    return {
        "source": "reviewed_xlsm_history",
        "source_files_count": len(per_file_results),
        "source_files": [result["file"] for result in per_file_results],
        "summary": {
            "total_descriptions": len(description_entries),
            "single_mapping_descriptions": single_mapping_count,
            "multi_mapping_descriptions": multi_mapping_count,
            "cross_statement_side_descriptions": cross_statement_side_count,
        },
        "descriptions": description_entries,
    }


if __name__ == "__main__":
    xlsm_files = (
        sorted(MAPPED_T12_DOCS_DIR.glob("*.xlsm")) +
        sorted(NEW_MAPPED_T12_DOCS_DIR.glob("*.xlsm"))
    )
    xlsm_files = [f for f in xlsm_files if not f.name.startswith("~$")]

    if not xlsm_files:
        raise FileNotFoundError("No reviewed .xlsm files found in mapped_T12_docs directories")

    print(f"Found {len(xlsm_files)} reviewed xlsm source file(s)\n")

    per_file_results = []

    for file_path in xlsm_files:
        result = extract_file(file_path)
        per_file_results.append(result)

        out_path = REVIEWED_ROW_HISTORY_PER_FILE_DIR / file_path.with_suffix(".json").name
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        print(f"  {result['file']}")
        print(
            f"    Rows: {result['total_rows']}  "
            f"(override: {result['override_rows']}, auto: {result['auto_rows']})  "
            f"unique descriptions: {result['unique_row_descriptions']}"
        )

    history_index = build_history_index(per_file_results)

    with open(REVIEWED_ROW_HISTORY_INDEX_PATH, "w") as f:
        json.dump(history_index, f, indent=2)

    print("\nHistory index summary:")
    print(f"  Total descriptions:           {history_index['summary']['total_descriptions']}")
    print(f"  Single-mapping descriptions:  {history_index['summary']['single_mapping_descriptions']}")
    print(f"  Multi-mapping descriptions:   {history_index['summary']['multi_mapping_descriptions']}")
    print(f"  Cross-side descriptions:      {history_index['summary']['cross_statement_side_descriptions']}")
    print(f"\nSaved per-file outputs to: {REVIEWED_ROW_HISTORY_PER_FILE_DIR}")
    print(f"Saved history index to: {REVIEWED_ROW_HISTORY_INDEX_PATH}")
