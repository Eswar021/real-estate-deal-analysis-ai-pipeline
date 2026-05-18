"""
Stage 2 Runner — NOI Verification

Runs the full Stage 2 verification flow in order:
    2a+2b compute_noi  → actual_noi_dir/ + computed_noi_dir/
    2c    compare_noi  → noi_comparison_dir/

Usage:
    python src/pipeline/2_noi_verification/run_stage.py

Reads:
    output_docs/current_manifest.json  (all paths)
    manifest["l1"]["paths"]["ai_mapped_dir"]  (Stage 1 output)

Writes:
    manifest["l2"]["paths"] directories

Does not call an LLM.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CURRENT_DIR = Path(__file__).resolve().parent

if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from config.paths import MANIFEST_PATH


def run_stage_2() -> None:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"No manifest at {MANIFEST_PATH}. Run Stage 0 (manifest runner) first."
        )

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    ai_mapped_dir    = Path(manifest["l1"]["paths"]["ai_mapped_dir"])
    actual_noi_dir   = Path(manifest["l2"]["paths"]["actual_noi_dir"])
    computed_noi_dir = Path(manifest["l2"]["paths"]["computed_noi_dir"])
    noi_comparison_dir = Path(manifest["l2"]["paths"]["noi_comparison_dir"])

    import compare_noi
    import compute_noi

    ai_mapped_files = sorted(ai_mapped_dir.glob("*.json"))
    if not ai_mapped_files:
        raise FileNotFoundError(f"No files found in {ai_mapped_dir}")

    print("Stage 2a + 2b — compute_noi")
    for json_file in ai_mapped_files:
        with open(json_file) as f:
            file_data = json.load(f)

        actual_result = compute_noi.extract_actual_noi(file_data)
        with open(actual_noi_dir / json_file.name, "w") as f:
            json.dump(actual_result, f, indent=2)

        computed_result = compute_noi.compute_noi(file_data)
        with open(computed_noi_dir / json_file.name, "w") as f:
            json.dump(computed_result, f, indent=2)

        print(f"  {computed_result['file']}")
        print(f"    Computed NOI: ${computed_result['computed_total_noi']:,.2f}")

    print("\nStage 2c — compare_noi")
    actual_files = sorted(actual_noi_dir.glob("*.json"))
    if not actual_files:
        raise FileNotFoundError(f"No files found in {actual_noi_dir}")

    for actual_path in actual_files:
        computed_path = computed_noi_dir / actual_path.name
        if not computed_path.exists():
            raise FileNotFoundError(f"Missing computed NOI file for {actual_path.name}")

        with open(actual_path) as f:
            actual_data = json.load(f)
        with open(computed_path) as f:
            computed_data = json.load(f)

        result = compare_noi.compare(actual_data, computed_data)
        out_path = noi_comparison_dir / actual_path.name
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2)

        status = "PASS" if result["overall_pass"] else "FAIL"
        print(f"  {status}  {result['file']}")
        print(f"    Difference: ${result['total_abs_diff']:,.2f}")


if __name__ == "__main__":
    run_stage_2()
