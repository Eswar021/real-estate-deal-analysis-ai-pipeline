"""
Stage 1 Runner — Mapping

Runs the full Stage 1 mapping flow in order:
    detect_blocks -> map_blocks -> find_mapping

Usage:
    python pipeline/1_mapping/run_stage.py
    python pipeline/1_mapping/run_stage.py --ai-limit 5

Notes:
    - The active runtime rulebook comes from config/rulebook_runtime.py.
    - The AI model/provider comes from config/agent_llm_config.py.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CURRENT_DIR = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from config.paths import AUTO_MAPPED_DIR, AI_MAPPED_DIR, BLOCK_DETECTION_DIR, INPUT_T12_DOCS_DIR


def run_stage_1(ai_limit: int | None = None) -> None:
    import detect_blocks
    import find_mapping
    import map_blocks

    input_files = sorted(
        [f for f in INPUT_T12_DOCS_DIR.glob("*.xlsx") if not f.name.startswith("~$")]
    )
    if not input_files:
        raise FileNotFoundError(f"No .xlsx files found in {INPUT_T12_DOCS_DIR}")

    print("Stage 1a — detect_blocks")
    for file_path in input_files:
        result = detect_blocks.classify_file(file_path)
        out_path = BLOCK_DETECTION_DIR / f"{file_path.stem}.json"
        with open(out_path, "w") as fp:
            json.dump(result, fp, indent=2)
        print(f"Saved results to {out_path}")

    print("\nStage 1b — map_blocks")
    from config.rulebook_utils import load_rulebook
    rulebook = load_rulebook(map_blocks.ACTIVE_RULEBOOK_PATH)
    detection_files = sorted(BLOCK_DETECTION_DIR.glob("*.json"))
    if not detection_files:
        raise FileNotFoundError(f"No JSON files found in {BLOCK_DETECTION_DIR}")

    for json_file in detection_files:
        with open(json_file, "r") as fp:
            entry = json.load(fp)

        mapped_entry = map_blocks.map_results(entry, rulebook)
        out_path = AUTO_MAPPED_DIR / json_file.name
        with open(out_path, "w") as fp:
            json.dump(mapped_entry, fp, indent=2)

        summary = mapped_entry["summary"]
        print(f"  {mapped_entry['file']}")
        print(
            f"    Data: {summary['data_rows']} | "
            f"Mapped: {summary['mapped']} | Unmapped: {summary['unmapped']}"
        )

    print("\nStage 1c — find_mapping")
    auto_mapped_files = sorted(AUTO_MAPPED_DIR.glob("*.json"))
    if not auto_mapped_files:
        raise FileNotFoundError(f"No JSON files found in {AUTO_MAPPED_DIR}")

    for json_file in auto_mapped_files:
        with open(json_file, "r") as fp:
            file_data = json.load(fp)

        updated_data = find_mapping.run_ai_mapping(file_data, limit=ai_limit)
        out_path = AI_MAPPED_DIR / json_file.name
        with open(out_path, "w") as fp:
            json.dump(updated_data, fp, indent=2)
        print(f"Saved AI mapped results to {out_path}")


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
