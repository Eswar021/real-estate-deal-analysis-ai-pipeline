"""
T12 Mapping Pipeline — Master Runner

Runs any combination of the numbered stages using the stage runners.

Usage:
    python src/pipeline/run_pipeline.py --stages 0,1,2
    python src/pipeline/run_pipeline.py --stages 1,2
    python src/pipeline/run_pipeline.py --from-stage 0 --to-stage 2
    python src/pipeline/run_pipeline.py --from-stage 1 --to-stage 2
    python src/pipeline/run_pipeline.py --stages 1 --ai-limit 5

Notes:
    - There is no default stage selection. Pass the stage config explicitly.
    - Stage numbering matches the folder naming:
        0 = manifest   (writes current_manifest.json + dated run_manifest.json)
        1 = detection  (detect_blocks → annotate_totals → compute_noi → compare_noi)
        2 = mapping    (map_blocks → find_mapping)
    - Stages 1 and 2 read all paths from current_manifest.json — no date recomputation.
    - To run only stages 1+2, a manifest from a prior Stage 0 run must exist.
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from pipeline.runner_utils import run_python_script

STAGE_RUNNERS = {
    0: PROJECT_ROOT / "src/pipeline/0_manifest/runner.py",
    1: PROJECT_ROOT / "src/pipeline/1_detection/run_stage.py",
    2: PROJECT_ROOT / "src/pipeline/2_mapping/run_stage.py",
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
    print(f"Running stages: {stages}")

    for stage in stages:
        runner_path = STAGE_RUNNERS[stage]
        runner_args: list[str] = []

        if stage == 2 and ai_limit is not None:
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
        help="Optional per-file limit forwarded to the Stage 2 AI mapping runner.",
    )
    args = parser.parse_args()

    try:
        selected_stages = resolve_stages(args)
    except ValueError as exc:
        parser.error(str(exc))

    run_pipeline(stages=selected_stages, ai_limit=args.ai_limit)
