"""
Stage 2 Runner — Mapping

Runs the full Stage 2 mapping flow in order:
    2a map_blocks   -> auto_mapped_dir/   (rulebook lookup)
    2b find_mapping -> ai_mapped_dir/     (AI fallback for unmapped rows)

Usage:
    python src/pipeline/2_mapping/run_stage.py
    python src/pipeline/2_mapping/run_stage.py --ai-limit 5

Reads:
    output_docs/current_manifest.json          (all paths, rulebook, AI config)
    manifest["l1"]["paths"]["annotated_blocks_dir"]  (Stage 1 output — annotated JSONs)

Writes:
    manifest["l2"]["paths"] directories

Calls an LLM (Stage 2b only).
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

import find_mapping
import map_blocks


def run_stage_2(ai_limit: int | None = None) -> None:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"No manifest at {MANIFEST_PATH}. Run Stage 0 (manifest runner) first."
        )

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    rulebook = manifest["rulebook"]
    l2_paths = manifest["l2"]["paths"]

    annotated_blocks_dir = Path(manifest["l1"]["paths"]["annotated_blocks_dir"])
    auto_mapped_dir      = Path(l2_paths["auto_mapped_dir"])
    ai_mapped_dir        = Path(l2_paths["ai_mapped_dir"])
    ai_mapping_logs_dir  = Path(l2_paths["ai_mapping_logs_dir"])

    annotated_files = sorted(annotated_blocks_dir.glob("*.json"))
    if not annotated_files:
        raise FileNotFoundError(f"No JSON files in {annotated_blocks_dir}")

    # ── 2a: map_blocks ───────────────────────────────────────────────────────
    print("Stage 2a — map_blocks")
    for json_file in annotated_files:
        with open(json_file) as fp:
            entry = json.load(fp)

        mapped_entry = map_blocks.map_results(entry, rulebook)
        out_path = auto_mapped_dir / json_file.name
        with open(out_path, "w") as fp:
            json.dump(mapped_entry, fp, indent=2)

        summary = mapped_entry["summary"]
        print(
            f"  {mapped_entry['file']}"
            f"  Data: {summary['data_rows']} | Mapped: {summary['mapped']} | Unmapped: {summary['unmapped']}"
        )

    # ── 2b: find_mapping (AI fallback) ───────────────────────────────────────
    print("\nStage 2b — find_mapping (AI)")
    auto_mapped_files = sorted(auto_mapped_dir.glob("*.json"))
    if not auto_mapped_files:
        raise FileNotFoundError(f"No JSON files in {auto_mapped_dir}")

    for json_file in auto_mapped_files:
        with open(json_file) as fp:
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
    run_stage_2(ai_limit=args.ai_limit)
