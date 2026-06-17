"""
Stage 1 Runner — Detection + NOI Verification

Runs the full Stage 1 detection flow in order:
    1a detect_blocks    -> block_detection_dir/
    1b annotate_totals  -> annotated_blocks_dir/   (is_total_revenue/expense/noi flags)
    1c compute_noi      -> actual_noi_dir/ + computed_noi_dir/
    1d compare_noi      -> noi_comparison_dir/

Usage:
    python src/pipeline/1_detection/run_stage.py

Reads:
    output_docs/current_manifest.json  (all paths + input files)
    data/input_T12_docs/*.xlsx         (via manifest["l1"]["input_files"])

Writes:
    manifest["l1"]["paths"] directories

Does not call an LLM.
"""

import json
from pathlib import Path

from t12_pipeline.config.paths import MANIFEST_PATH
from t12_pipeline.pipeline.detection import (
    annotate_totals,
    compare_noi,
    compute_noi,
    detect_blocks,
)


def run_stage_1() -> None:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"No manifest at {MANIFEST_PATH}. Run Stage 0 (manifest runner) first."
        )

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    l1_paths = manifest["l1"]["paths"]
    input_files = [
        Path(p) for p in manifest["l1"]["input_files"]
        if not Path(p).name.startswith("~$")
    ]

    block_detection_dir  = Path(l1_paths["block_detection_dir"])
    annotated_blocks_dir = Path(l1_paths["annotated_blocks_dir"])
    actual_noi_dir       = Path(l1_paths["actual_noi_dir"])
    computed_noi_dir     = Path(l1_paths["computed_noi_dir"])
    noi_comparison_dir   = Path(l1_paths["noi_comparison_dir"])

    # ── 1a: detect_blocks ────────────────────────────────────────────────────
    print("Stage 1a — detect_blocks")
    for file_path in input_files:
        result = detect_blocks.classify_file(file_path)
        out_path = block_detection_dir / f"{file_path.stem}.json"
        with open(out_path, "w") as fp:
            json.dump(result, fp, indent=2)
        print(f"  {result['file']}  ({result['format']})")

    # ── 1b: annotate_totals ──────────────────────────────────────────────────
    print("\nStage 1b — annotate_totals")
    annotate_totals.annotate_all(block_detection_dir, annotated_blocks_dir)

    # ── 1c: compute_noi ──────────────────────────────────────────────────────
    print("\nStage 1c — compute_noi")
    annotated_files = sorted(annotated_blocks_dir.glob("*.json"))
    if not annotated_files:
        raise FileNotFoundError(f"No JSON files in {annotated_blocks_dir}")

    for jfile in annotated_files:
        with open(jfile) as fp:
            file_data = json.load(fp)

        actual = compute_noi.extract_actual_noi(file_data)
        with open(actual_noi_dir / jfile.name, "w") as fp:
            json.dump(actual, fp, indent=2)

        computed = compute_noi.compute_noi(file_data)
        with open(computed_noi_dir / jfile.name, "w") as fp:
            json.dump(computed, fp, indent=2)

        print(f"  {computed['file']}  NOI: ${computed['noi']['total']:,.2f}")

    # ── 1d: compare_noi ──────────────────────────────────────────────────────
    print("\nStage 1d — compare_noi")
    actual_files = sorted(actual_noi_dir.glob("*.json"))
    if not actual_files:
        raise FileNotFoundError(f"No files in {actual_noi_dir}")

    pass_count = 0
    fail_count = 0

    for actual_path in actual_files:
        computed_path = computed_noi_dir / actual_path.name
        if not computed_path.exists():
            raise FileNotFoundError(f"Missing computed NOI file: {actual_path.name}")

        with open(actual_path) as fp:
            actual_data = json.load(fp)
        with open(computed_path) as fp:
            computed_data = json.load(fp)

        result = compare_noi.compare(actual_data, computed_data)

        out_path = noi_comparison_dir / actual_path.name
        with open(out_path, "w") as fp:
            json.dump(result, fp, indent=2)

        status = "PASS" if result["overall_pass"] else "FAIL"
        print(f"  {status}  {result['file']}  diff=${(result['totals']['noi']['abs_diff'] or 0):,.2f}")
        if result["overall_pass"]:
            pass_count += 1
        else:
            fail_count += 1

    print(f"\n  NOI: {pass_count} PASS  {fail_count} FAIL  ({pass_count + fail_count} total)")


if __name__ == "__main__":
    run_stage_1()
