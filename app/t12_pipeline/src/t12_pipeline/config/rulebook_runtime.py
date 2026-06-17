from pathlib import Path

from t12_pipeline.config.paths import RULEBOOK_DB_OUTPUT_PATH


# Module names invoked via `python -m`. Each maps to one stage of rulebook construction.
RULEBOOK_BUILDER_MODULES = [
    "t12_pipeline.build_rulebook.build_client_review_rules",
    "t12_pipeline.build_rulebook.extract_reviewed_row_history",
    "t12_pipeline.build_rulebook.build_historical_rule_support",
    "t12_pipeline.build_rulebook.build_rulebook",
]


def get_rulebook_built_output_path() -> Path:
    return RULEBOOK_DB_OUTPUT_PATH


def get_rulebook_builder_modules() -> list[str]:
    return list(RULEBOOK_BUILDER_MODULES)
