"""
Stage 0 Runner — Build Rulebook

Runs the configured rulebook build approach for Stage 0.

Usage:
    python pipeline/0_build_rulebook/run_stage.py

Notes:
    - The active rulebook profile comes from config/rulebook_runtime.py.
    - Both v1 and v2 builders write to output_docs only.
    - db/ is treated as read-only reference storage, not a write target.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.rulebook_runtime import (
    get_active_rulebook_name,
    get_rulebook_built_output_path,
    get_rulebook_profile,
)
from pipeline.runner_utils import run_python_script


def run_stage_0() -> None:
    profile_name = get_active_rulebook_name()
    profile = get_rulebook_profile(profile_name)
    built_output_path = get_rulebook_built_output_path(profile_name)

    print(f"Running Stage 0 with rulebook profile: {profile_name}")
    print(f"  Label: {profile['label']}")
    print(f"  Output rulebook path: {built_output_path}")

    for script_rel in profile["builder_scripts"]:  # type: ignore[index]
        run_python_script(PROJECT_ROOT / script_rel)

    if not built_output_path.exists():
        raise FileNotFoundError(f"Built rulebook output not found at {built_output_path}")

    run_python_script(PROJECT_ROOT / "pipeline/0_build_rulebook/category_config.py")


if __name__ == "__main__":
    run_stage_0()
