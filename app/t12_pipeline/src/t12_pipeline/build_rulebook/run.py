"""
Build Rulebook Runner

Runs the full rulebook build chain. Run this once when new reviewed
.xlsm files arrive. The output goes to db/rulebooks/ and is picked up
by the manifest runner (Stage 0) on the next pipeline run.

Usage:
    python -m t12_pipeline.build_rulebook.run

Reads:
    data/client_review_docs/  (client-reviewed .xlsm workbooks)
    output_docs/<timestamp>/build_rulebook/  (intermediate artifacts)

Writes:
    db/rulebooks/mapping_rulebook_<timestamp>.json
"""

from t12_pipeline.config.rulebook_runtime import (
    get_rulebook_builder_modules,
    get_rulebook_built_output_path,
)
from t12_pipeline.pipeline.runner_utils import run_python_module


def run() -> None:
    built_output_path = get_rulebook_built_output_path()

    print("Running rulebook build chain")
    print(f"  Output: {built_output_path}")

    for module in get_rulebook_builder_modules():
        run_python_module(module)

    if not built_output_path.exists():
        raise FileNotFoundError(f"Built rulebook not found at {built_output_path}")


if __name__ == "__main__":
    run()
