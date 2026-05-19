from pathlib import Path

from config.paths import RULEBOOK_DB_OUTPUT_PATH


RULEBOOK_BUILDER_SCRIPTS = [
    "src/build_rulebook/build_client_review_rules.py",
    "src/build_rulebook/extract_reviewed_row_history.py",
    "src/build_rulebook/build_historical_rule_support.py",
    "src/build_rulebook/build_rulebook.py",
]


def get_rulebook_built_output_path() -> Path:
    return RULEBOOK_DB_OUTPUT_PATH


def get_rulebook_builder_scripts() -> list[str]:
    return list(RULEBOOK_BUILDER_SCRIPTS)
