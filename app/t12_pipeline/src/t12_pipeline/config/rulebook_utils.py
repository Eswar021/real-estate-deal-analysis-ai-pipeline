import json
import re
from collections import defaultdict
from pathlib import Path


RULEBOOK_SECTION_KEYS = {"certain", "contextual", "no_conflict", "unresolved"}

# A leading account-code prefix in ANY vendor style, followed by the description:
#   `5120 - Rent`  `4030-000 - Rent`  `33010 - Rent`  `1-5000-0005 Rent`  `5120.0000 Rent`
#   `4010:Rent`  `5120 Gross Rent` (space-separated, Chateau)
# This runs ONLY at rulebook lookup (map_blocks) — the pipeline's `description` keeps the code,
# so classification / anchors / NOI are unaffected. The rulebook's own keys are already
# code-free, so stripping the query here is what makes an embedded-code row (Reserve/Trails
# `33010 - Vacancy Loss`) match the clean key `vacancy loss`.
#
# The dash / dot / colon separator is mandatory in those branches. The SPACE-separated branch is
# looser (the space is the only separator), so it is fenced: 4-6 digits (a 3-digit `911 Phone`
# is left alone), and a negative lookahead drops 19xx/20xx so a real leading YEAR ("2024 Budget")
# is never stripped. Verified against the corpus: the only non-year leading `\d{4,6} text` cells
# are Chateau's account codes.
_CODE_PREFIX = re.compile(
    r"^\s*(?:"
    r"\d-\d{4}-\d+"                        # MRI          1-5000-0005
    r"|\d{4,6}\s*-\s*\d*\s*-?"              # dashed       5120- / 4030-000- / 33010 -
    r"|\d{4,6}[.:]\d*"                     # dotted/colon 5120.0000 / 4010:
    r"|(?!(?:19|20)\d\d\b)\d{4,6}(?=\s+\D)"  # space-only   5120 Gross  (NOT a 19xx/20xx year)
    r")\s*(?:[-–]\s*)?"                    # trailing whitespace + an optional dash (5295.008 - Desc)
)


def normalize_lookup_key(text: str) -> str:
    return _CODE_PREFIX.sub("", text).strip().lower()


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


def load_latest_rulebook() -> dict:
    """The newest mapping_rulebook_*.json in db/rulebooks/ — what Stage 3 maps against.
    Lives here (not in the UI) so the mapping stage is runnable without Django."""
    from t12_pipeline.config.paths import DB_RULEBOOKS_DIR
    candidates = sorted(DB_RULEBOOKS_DIR.glob("mapping_rulebook_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No rulebook in {DB_RULEBOOKS_DIR}. "
            "Run `python -m t12_pipeline.build_rulebook.run` first.")
    return load_rulebook(candidates[-1])


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


def get_rulebook_examples(rulebook: dict, max_examples_per_category: int = 3) -> dict[str, list[str]]:
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
    for category in sorted(by_category.keys()):
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
