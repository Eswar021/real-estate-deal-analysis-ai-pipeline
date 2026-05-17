from pathlib import Path

from config.paths import RULEBOOK_DB_PATH, RULEBOOK_OUTPUT_PATH


ACTIVE_RULEBOOK_NAME = "main"
ACTIVE_RULEBOOK_PATH = RULEBOOK_OUTPUT_PATH
RULEBOOK_BASELINE_DB_PATH = RULEBOOK_DB_PATH

RULEBOOK_BUILDER_SCRIPTS = [
    "pipeline/0_build_rulebook/build_client_review_rules.py",
    "pipeline/0_build_rulebook/extract_reviewed_row_history.py",
    "pipeline/0_build_rulebook/build_historical_rule_support.py",
    "pipeline/0_build_rulebook/build_rulebook.py",
]


def get_active_rulebook_path() -> Path:
    return ACTIVE_RULEBOOK_PATH


def get_active_rulebook_name() -> str:
    return ACTIVE_RULEBOOK_NAME


def get_rulebook_built_output_path() -> Path:
    return ACTIVE_RULEBOOK_PATH


def get_rulebook_builder_scripts() -> list[str]:
    return list(RULEBOOK_BUILDER_SCRIPTS)
