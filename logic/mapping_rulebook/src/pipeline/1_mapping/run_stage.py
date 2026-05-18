"""
Stage 1 Runner — Mapping

Runs the full Stage 1 mapping flow in order:
    1a detect_blocks  → block_detection_dir/
    1b annotate_totals → annotated_blocks_dir/  (adds is_total_revenue/expense/noi flags)
    1c map_blocks     → auto_mapped_dir/
    1d find_mapping   → ai_mapped_dir/  (AI fallback for unmapped rows)

Usage:
    python src/pipeline/1_mapping/run_stage.py
    python src/pipeline/1_mapping/run_stage.py --ai-limit 5

Reads:
    output_docs/current_manifest.json  (all paths, rulebook, AI config)
    data/input_T12_docs/*.xlsx         (raw T12 files, via manifest["l1"]["input_files"])

Writes:
    manifest["l1"]["paths"] directories

Calls an LLM (Stage 1d only).
"""

import argparse
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


def run_stage_1(ai_limit: int | None = None) -> None:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"No manifest at {MANIFEST_PATH}. Run Stage 0 (manifest runner) first."
        )

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    rulebook = manifest["rulebook"]
    l1_paths = manifest["l1"]["paths"]
    input_files = [
        Path(p) for p in manifest["l1"]["input_files"]
        if not Path(p).name.startswith("~$")
    ]

    block_detection_dir  = Path(l1_paths["block_detection_dir"])
    annotated_blocks_dir = Path(l1_paths["annotated_blocks_dir"])
    auto_mapped_dir      = Path(l1_paths["auto_mapped_dir"])
    ai_mapped_dir        = Path(l1_paths["ai_mapped_dir"])
    ai_mapping_logs_dir  = Path(l1_paths["ai_mapping_logs_dir"])

    import detect_blocks
    import annotate_totals
    import find_mapping
    import map_blocks

    # ── 1a: detect_blocks ────────────────────────────────────────────────────
    print("Stage 1a — detect_blocks")
    for file_path in input_files:
        result = detect_blocks.classify_file(file_path)
        out_path = block_detection_dir / f"{file_path.stem}.json"
        with open(out_path, "w") as fp:
            json.dump(result, fp, indent=2)
        print(f"  Saved: {out_path.name}")

    # ── 1b: annotate_totals ──────────────────────────────────────────────────
    print("\nStage 1b — annotate_totals")
    annotate_totals.annotate_all(block_detection_dir, annotated_blocks_dir)

    # ── 1c: map_blocks ───────────────────────────────────────────────────────
    print("\nStage 1c — map_blocks")
    annotated_files = sorted(annotated_blocks_dir.glob("*.json"))
    if not annotated_files:
        raise FileNotFoundError(f"No JSON files in {annotated_blocks_dir}")

    for json_file in annotated_files:
        with open(json_file, "r") as fp:
            entry = json.load(fp)

        mapped_entry = map_blocks.map_results(entry, rulebook)
        out_path = auto_mapped_dir / json_file.name
        with open(out_path, "w") as fp:
            json.dump(mapped_entry, fp, indent=2)

        summary = mapped_entry["summary"]
        print(f"  {mapped_entry['file']}")
        print(
            f"    Data: {summary['data_rows']} | "
            f"Mapped: {summary['mapped']} | Unmapped: {summary['unmapped']}"
        )

    # ── 1d: find_mapping (AI fallback) ───────────────────────────────────────
    print("\nStage 1d — find_mapping (AI)")
    auto_mapped_files = sorted(auto_mapped_dir.glob("*.json"))
    if not auto_mapped_files:
        raise FileNotFoundError(f"No JSON files in {auto_mapped_dir}")

    for json_file in auto_mapped_files:
        with open(json_file, "r") as fp:
            file_data = json.load(fp)

        updated_data = find_mapping.run_ai_mapping(
            file_data, rulebook, ai_mapping_logs_dir, limit=ai_limit
        )
        out_path = ai_mapped_dir / json_file.name
        with open(out_path, "w") as fp:
            json.dump(updated_data, fp, indent=2)
        print(f"  Saved: {out_path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ai-limit",
        type=int,
        default=None,
        help="Optional per-file limit for unmapped rows sent to the AI agent.",
    )
    args = parser.parse_args()
    run_stage_1(ai_limit=args.ai_limit)
