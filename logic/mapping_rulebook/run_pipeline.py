"""
T12 Mapping Pipeline — Master Runner

Runs any combination of the numbered stages using the stage runners.

Usage:
    python run_pipeline.py --stages 0,1,2
    python run_pipeline.py --stages 1,2
    python run_pipeline.py --from-stage 0 --to-stage 2
    python run_pipeline.py --from-stage 1 --to-stage 2
    python run_pipeline.py --stages 1 --ai-limit 5

Notes:
    - There is no default stage selection. Pass the stage config explicitly.
    - Stage numbering matches the folder naming:
        0 = build_rulebook
        1 = mapping
        2 = noi_verification
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.rulebook_runtime import get_active_rulebook_name
from pipeline.runner_utils import run_python_script

STAGE_RUNNERS = {
    0: PROJECT_ROOT / "pipeline/0_build_rulebook/run_stage.py",
    1: PROJECT_ROOT / "pipeline/1_mapping/run_stage.py",
    2: PROJECT_ROOT / "pipeline/2_noi_verification/run_stage.py",
}


def resolve_stages(args) -> list[int]:
    if args.stages and (args.from_stage is not None or args.to_stage is not None):
        raise ValueError("Use either --stages or --from-stage/--to-stage, not both.")

    if args.stages:
        try:
            stages = sorted(int(part.strip()) for part in args.stages.split(","))
        except ValueError as exc:
            raise ValueError("--stages must be a comma-separated list like 0,1,2") from exc
    elif args.from_stage is not None and args.to_stage is not None:
        if args.from_stage > args.to_stage:
            raise ValueError("--from-stage cannot be greater than --to-stage.")
        stages = list(range(args.from_stage, args.to_stage + 1))
    else:
        raise ValueError(
            "Pass either --stages or both --from-stage and --to-stage. "
            "This runner does not assume default stages."
        )

    invalid = [stage for stage in stages if stage not in STAGE_RUNNERS]
    if invalid:
        raise ValueError(f"Unknown stages: {invalid}. Valid stages are 0, 1, 2.")

    return stages


def run_pipeline(stages: list[int], ai_limit: int | None = None) -> None:
    active_rulebook = get_active_rulebook_name()

    print(f"Running stages: {stages}")
    print(f"Active runtime rulebook: {active_rulebook}")

    for stage in stages:
        runner_path = STAGE_RUNNERS[stage]
        runner_args: list[str] = []

        if stage == 1 and ai_limit is not None:
            runner_args.extend(["--ai-limit", str(ai_limit)])

        print(f"\n=== Stage {stage} ===")
        run_python_script(runner_path, runner_args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stages",
        help="Comma-separated explicit stage list, for example: 0,1,2 or 1,2",
    )
    parser.add_argument(
        "--from-stage",
        type=int,
        default=None,
        help="Start stage number for an explicit range.",
    )
    parser.add_argument(
        "--to-stage",
        type=int,
        default=None,
        help="End stage number for an explicit range.",
    )
    parser.add_argument(
        "--ai-limit",
        type=int,
        default=None,
        help="Optional per-file limit forwarded to the Stage 1 AI mapping runner.",
    )
    args = parser.parse_args()

    try:
        selected_stages = resolve_stages(args)
    except ValueError as exc:
        parser.error(str(exc))

    run_pipeline(stages=selected_stages, ai_limit=args.ai_limit)
