"""
map_blocks.py — Stage 1c

Reads annotated block-detection JSON, looks up each data row's description
in the mapping rulebook, and produces auto-mapped JSON with mapping info added.

Reads:
    manifest["l1"]["paths"]["annotated_blocks_dir"]  (per-file JSON)
    manifest["rulebook"]                             (passed in directly)

Writes:
    manifest["l1"]["paths"]["auto_mapped_dir"]       (per-file JSON)

Does not call an LLM.
"""

import json
from pathlib import Path

from t12_pipeline.config.rulebook_utils import normalize_lookup_key


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


_UNSET = object()


def apply_row_edit(mapped, row_number, category=_UNSET, flip_sign=_UNSET, valid_categories=None):
    """The user's override of ONE mapped data row (data_review). Returns a copy of `mapped`
    with ONLY the passed fields written. Deliberately does not re-map or call the AI — the
    user is the authority here.

    Pass a field only when the user actually changed it: the page posts the whole row on every
    edit, so writing both would stamp final_mapping — a USER override — onto a row whose
    category the rulebook or the AI picked and the user never touched. `category=None` is an
    explicit "clear my override", distinct from not passing it at all. (Stage 2's class edits
    are diffed the same way.)

    Raises ValueError if the row isn't a mapped data row, or the category isn't in the
    rulebook — mirroring Stage 2, where apply_corrections refuses a class outside CLASSES.
    """
    if category not in (_UNSET, None) and valid_categories is not None \
            and category not in valid_categories:
        raise ValueError(f"Unknown category: {category!r}")

    out = {**mapped, "rows": [dict(r) for r in mapped.get("rows", [])]}
    for r in out["rows"]:
        if r.get("row") == row_number and r.get("type") == "data":
            if category is not _UNSET:
                r["final_mapping"] = category or None
            if flip_sign is not _UNSET:
                r["flip_sign"] = bool(flip_sign)
            return out
    raise ValueError(f"Row {row_number} not found in mapped data")


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
    from config.paths import MANIFEST_PATH

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"No manifest at {MANIFEST_PATH}. Run Stage 0 first.")

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    rulebook = manifest["rulebook"]
    annotated_blocks_dir = Path(manifest["l1"]["paths"]["annotated_blocks_dir"])
    auto_mapped_dir = Path(manifest["l1"]["paths"]["auto_mapped_dir"])
    auto_mapped_dir.mkdir(parents=True, exist_ok=True)

    summary_rb = rulebook.get("summary", {})
    print(
        f"Rulebook: certain={len(rulebook.get('certain', {}))}, "
        f"contextual={len(rulebook.get('contextual', {}))}, "
        f"no_conflict={len(rulebook.get('no_conflict', {}))}, "
        f"unresolved={len(rulebook.get('unresolved', {}))}"
    )

    json_files = sorted(annotated_blocks_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No JSON files found in {annotated_blocks_dir}")

    for f in json_files:
        with open(f, "r") as fp:
            entry = json.load(fp)

        mapped_entry = map_results(entry, rulebook=rulebook)

        s = mapped_entry["summary"]
        print(f"  {mapped_entry['file']}")
        print(f"    Data: {s['data_rows']} | Mapped: {s['mapped']} | Unmapped: {s['unmapped']}")

        out_path = auto_mapped_dir / f.name
        with open(out_path, "w") as fp:
            json.dump(mapped_entry, fp, indent=2)

    print(f"\nSaved mapped results → {auto_mapped_dir}")
