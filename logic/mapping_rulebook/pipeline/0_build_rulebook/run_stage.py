"""
Stage 0 Runner — Build Rulebook

Runs the single current rulebook build flow for Stage 0.

Usage:
    python pipeline/0_build_rulebook/run_stage.py

Notes:
    - The active rulebook path comes from config/rulebook_runtime.py.
    - db/ is treated as read-only reference storage, not a write target.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.rulebook_runtime import (
    get_active_rulebook_name,
    get_rulebook_builder_scripts,
    get_rulebook_built_output_path,
)
from pipeline.runner_utils import run_python_script


def run_stage_0() -> None:
    rulebook_name = get_active_rulebook_name()
    built_output_path = get_rulebook_built_output_path()

    print(f"Running Stage 0 with rulebook: {rulebook_name}")
    print(f"  Output rulebook path: {built_output_path}")

    for script_rel in get_rulebook_builder_scripts():
        run_python_script(PROJECT_ROOT / script_rel)

    if not built_output_path.exists():
        raise FileNotFoundError(f"Built rulebook output not found at {built_output_path}")

    run_python_script(PROJECT_ROOT / "pipeline/0_build_rulebook/category_config.py")


if __name__ == "__main__":
    run_stage_0()
