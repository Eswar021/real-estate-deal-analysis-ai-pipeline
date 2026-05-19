"""
Build Rulebook Runner

Runs the full rulebook build chain. Run this once when new reviewed
.xlsm files arrive. The output goes to db/rulebooks/ and is picked up
by the manifest runner (Stage 0) on the next pipeline run.

Usage:
    python src/build_rulebook/run.py

Reads:
    data/client_review_docs/  (client-reviewed .xlsm workbooks)
    output_docs/<timestamp>/build_rulebook/  (intermediate artifacts)

Writes:
    db/rulebooks/mapping_rulebook_<timestamp>.json
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.rulebook_runtime import (
    get_rulebook_builder_scripts,
    get_rulebook_built_output_path,
)
from pipeline.runner_utils import run_python_script


def run() -> None:
    built_output_path = get_rulebook_built_output_path()

    print("Running rulebook build chain")
    print(f"  Output: {built_output_path}")

    for script_rel in get_rulebook_builder_scripts():
        run_python_script(PROJECT_ROOT / script_rel)

    if not built_output_path.exists():
        raise FileNotFoundError(f"Built rulebook not found at {built_output_path}")


if __name__ == "__main__":
    run()
