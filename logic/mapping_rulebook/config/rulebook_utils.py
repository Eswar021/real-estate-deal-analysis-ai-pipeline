import json
from collections import defaultdict
from pathlib import Path


RULEBOOK_SECTION_KEYS = {"certain", "contextual", "no_conflict", "unresolved"}


def normalize_lookup_key(text: str) -> str:
    return text.strip().lower()


def normalize_section_key(text: str) -> str:
    return " ".join(text.strip().lower().split())


def build_section_path_key(section_path: list[str]) -> str:
    return " > ".join(
        normalize_section_key(part)
        for part in section_path
        if part and part.strip()
    )


def load_rulebook(rulebook_path: Path) -> dict:
    with open(rulebook_path, "r") as f:
        return json.load(f)


def validate_rulebook(rulebook: dict) -> None:
    missing = RULEBOOK_SECTION_KEYS - set(rulebook.keys())
    if missing:
        raise ValueError(f"Rulebook is missing required sections: {sorted(missing)}")


def get_rulebook_categories(rulebook: dict) -> list[str]:
    validate_rulebook(rulebook)

    categories = set()

    for entry in rulebook["certain"].values():
        categories.add(entry["mapping"])

    for entry in rulebook["no_conflict"].values():
        categories.add(entry["mapping"])

    for entry in rulebook["contextual"].values():
        if entry["rule_type"] == "statement_side":
            categories.update(entry["conditions"].values())
        elif entry["rule_type"] == "section_rule":
            categories.add(entry["default_mapping"])
            for section_rule in entry["section_rules"]:
                categories.add(section_rule["mapping"])

    return sorted(categories)


def get_rulebook_examples(rulebook: dict, max_categories: int = 10, max_examples_per_category: int = 3) -> dict[str, list[str]]:
    validate_rulebook(rulebook)

    by_category: dict[str, list[str]] = defaultdict(list)

    for entry in rulebook["certain"].values():
        by_category[entry["mapping"]].append(entry["row_description"])

    for entry in rulebook["no_conflict"].values():
        by_category[entry["mapping"]].append(entry["row_description"])

    for entry in rulebook["contextual"].values():
        if entry["rule_type"] == "statement_side":
            for mapping in entry["conditions"].values():
                by_category[mapping].append(entry["row_description"])
        elif entry["rule_type"] == "section_rule":
            by_category[entry["default_mapping"]].append(entry["row_description"])
            for section_rule in entry["section_rules"]:
                by_category[section_rule["mapping"]].append(entry["row_description"])

    examples = {}
    for category in sorted(by_category.keys())[:max_categories]:
        seen = []
        for desc in by_category[category]:
            if desc not in seen:
                seen.append(desc)
        examples[category] = seen[:max_examples_per_category]

    return examples


def flatten_rulebook_rows(rulebook: dict) -> list[dict]:
    validate_rulebook(rulebook)

    rows = []

    for entry in rulebook["certain"].values():
        rows.append({
            "rulebook_section": "certain",
            "row_description": entry["row_description"],
            "mapping": entry["mapping"],
            "rule_type": "direct",
            "rule_detail": None,
        })

    for entry in rulebook["no_conflict"].values():
        rows.append({
            "rulebook_section": "no_conflict",
            "row_description": entry["row_description"],
            "mapping": entry["mapping"],
            "rule_type": "direct",
            "rule_detail": None,
        })

    for entry in rulebook["contextual"].values():
        if entry["rule_type"] == "statement_side":
            for side, mapping in sorted(entry["conditions"].items()):
                rows.append({
                    "rulebook_section": "contextual",
                    "row_description": entry["row_description"],
                    "mapping": mapping,
                    "rule_type": "statement_side",
                    "rule_detail": side,
                })
        elif entry["rule_type"] == "section_rule":
            rows.append({
                "rulebook_section": "contextual",
                "row_description": entry["row_description"],
                "mapping": entry["default_mapping"],
                "rule_type": "section_rule_default",
                "rule_detail": None,
            })
            for section_rule in entry["section_rules"]:
                rows.append({
                    "rulebook_section": "contextual",
                    "row_description": entry["row_description"],
                    "mapping": section_rule["mapping"],
                    "rule_type": "section_rule_match",
                    "rule_detail": section_rule["section_contains"],
                })

    for entry in rulebook["unresolved"].values():
        rows.append({
            "rulebook_section": "unresolved",
            "row_description": entry["row_description"],
            "mapping": None,
            "rule_type": "ai_review",
            "rule_detail": entry.get("reason_type"),
        })

    return rows
