"""
Manifest Runner — Stage 0

Writes the run manifest that all downstream stages read from.
Fixes the date-rollover bug: stages 1 and 2 read absolute paths from
the manifest rather than recomputing date-stamped paths at import time.

Usage:
    python src/pipeline/0_manifest/runner.py

Reads:
    db/rulebooks/  (picks the latest mapping_rulebook_*.json by filename)
    data/input_T12_docs/  (all .xlsx files)
    config/agent_llm_config.py  (AI provider/model for Stage 1)

Writes:
    output_docs/<timestamp>/run_manifest.json  (frozen per-run snapshot)
    output_docs/current_manifest.json          (always-latest pointer)

Does not call an LLM.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.agent_llm_config import MAPPING_AI_AGENT, get_agent_llm_config
from config.paths import (
    AI_MAPPED_DIR,
    AI_MAPPING_LOGS_DIR,
    ANNOTATED_BLOCKS_DIR,
    AUTO_MAPPED_DIR,
    ACTUAL_NOI_DIR,
    BLOCK_DETECTION_DIR,
    COMPUTED_NOI_DIR,
    DB_RULEBOOKS_DIR,
    INPUT_T12_DOCS_DIR,
    MANIFEST_PATH,
    NOI_COMPARISON_DIR,
    OUTPUT_DOCS_DIR,
)


def _pick_latest_rulebook() -> Path:
    candidates = sorted(DB_RULEBOOKS_DIR.glob("mapping_rulebook_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No rulebook found in {DB_RULEBOOKS_DIR}. "
            "Run `python src/build_rulebook/run.py` first."
        )
    return candidates[-1]


def _collect_input_files() -> list[str]:
    files = sorted(INPUT_T12_DOCS_DIR.glob("*.xlsx"))
    if not files:
        raise FileNotFoundError(f"No .xlsx files found in {INPUT_T12_DOCS_DIR}")
    return [str(f.resolve()) for f in files]


def build_manifest() -> dict:
    rulebook_path = _pick_latest_rulebook()
    with open(rulebook_path, "r") as f:
        rulebook = json.load(f)

    ai_cfg = get_agent_llm_config(MAPPING_AI_AGENT)

    run_timestamp = OUTPUT_DOCS_DIR.name
    run_id = f"RUN_{run_timestamp}"

    return {
        "metadata": {
            "run_date": run_timestamp[:10].replace("_", "-"),
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "output_base": str(OUTPUT_DOCS_DIR),
            "rulebook_source": str(rulebook_path),
            "rulebook_entries": (
                len(rulebook.get("certain", {})) +
                len(rulebook.get("contextual", {})) +
                len(rulebook.get("no_conflict", {})) +
                len(rulebook.get("unresolved", {}))
            ),
        },
        "rulebook": {
            "certain": rulebook["certain"],
            "contextual": rulebook["contextual"],
            "no_conflict": rulebook["no_conflict"],
            "unresolved": rulebook["unresolved"],
        },
        "l1": {
            "input_files": _collect_input_files(),
            "ai": {
                "provider": ai_cfg["provider"],
                "model": ai_cfg["model"],
                "temperature": ai_cfg["temperature"],
            },
            "paths": {
                "block_detection_dir": str(BLOCK_DETECTION_DIR),
                "annotated_blocks_dir": str(ANNOTATED_BLOCKS_DIR),
                "auto_mapped_dir": str(AUTO_MAPPED_DIR),
                "ai_mapped_dir": str(AI_MAPPED_DIR),
                "ai_mapping_logs_dir": str(AI_MAPPING_LOGS_DIR),
            },
        },
        "l2": {
            "paths": {
                "actual_noi_dir": str(ACTUAL_NOI_DIR),
                "computed_noi_dir": str(COMPUTED_NOI_DIR),
                "noi_comparison_dir": str(NOI_COMPARISON_DIR),
            },
        },
    }


def _create_output_dirs(manifest: dict) -> None:
    l1_paths = manifest["l1"]["paths"]
    l2_paths = manifest["l2"]["paths"]
    for path_str in list(l1_paths.values()) + list(l2_paths.values()):
        Path(path_str).mkdir(parents=True, exist_ok=True)


def run() -> None:
    manifest = build_manifest()

    _create_output_dirs(manifest)

    dated_manifest_path = OUTPUT_DOCS_DIR / "run_manifest.json"
    with open(dated_manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Manifest written")
    print(f"  Run ID:    {manifest['metadata']['run_id']}")
    print(f"  Rulebook:  {manifest['metadata']['rulebook_source']}")
    print(f"  Entries:   {manifest['metadata']['rulebook_entries']}")
    print(f"  Files:     {len(manifest['l1']['input_files'])}")
    print(f"  Output:    {manifest['metadata']['output_base']}")
    print(f"  Current:   {MANIFEST_PATH}")


if __name__ == "__main__":
    run()
