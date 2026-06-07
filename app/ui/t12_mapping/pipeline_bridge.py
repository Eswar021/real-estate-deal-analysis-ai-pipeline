"""
t12_mapping/pipeline_bridge.py

Thin wrapper that calls the t12_pipeline detection AND mapping functions
and persists each stage output via the storage abstraction (so dev=local
FS, prod=S3 is a one-line settings change).

The t12_pipeline package is installed in editable mode
(`pip install -e ./app/t12_pipeline`) — no sys.path manipulation needed.
"""

import json

from shared import storage

from t12_pipeline.config.paths import DB_RULEBOOKS_DIR
from t12_pipeline.config.rulebook_utils import get_rulebook_categories
from t12_pipeline.pipeline.detection.detect_blocks import classify_file
from t12_pipeline.pipeline.detection.annotate_totals import annotate_file
from t12_pipeline.pipeline.detection.compute_noi import compute_noi, extract_actual_noi
from t12_pipeline.pipeline.detection.compare_noi import compare
from t12_pipeline.pipeline.detection.corrections import (
    apply_corrections,
    recompute_noi as _recompute_noi,
)
from t12_pipeline.pipeline.mapping.map_blocks import map_results
from t12_pipeline.pipeline.mapping.find_mapping import run_ai_mapping


def _load_latest_rulebook() -> dict:
    """Pick the newest mapping_rulebook_*.json from db/rulebooks/ — same logic as Stage 0."""
    candidates = sorted(DB_RULEBOOKS_DIR.glob("mapping_rulebook_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No rulebook in {DB_RULEBOOKS_DIR}. "
            "Run `python -m t12_pipeline.build_rulebook.run` first."
        )
    with open(candidates[-1]) as f:
        return json.load(f)


def run_detection(upload_id, xlsx_local_path) -> dict:
    """
    Runs the full detection stage on a single Excel file.

    Steps:
        1. classify_file  → block_detection.json
        2. annotate_file  → annotated_blocks.json
        3. extract_actual_noi + compute_noi → actual_noi.json, computed_noi.json
        4. compare        → comparison.json

    Returns the comparison dict so the view can display PASS/FAIL and totals.
    """
    detection = classify_file(str(xlsx_local_path))
    storage.write_json(upload_id, "block_detection.json", detection)

    annotated = annotate_file(detection)
    storage.write_json(upload_id, "annotated_blocks.json", annotated)

    actual   = extract_actual_noi(annotated)
    computed = compute_noi(annotated)
    storage.write_json(upload_id, "actual_noi.json",   actual)
    storage.write_json(upload_id, "computed_noi.json", computed)

    comparison = compare(actual, computed)
    storage.write_json(upload_id, "comparison.json", comparison)

    return comparison


def apply_and_recompute(upload_id, corrections: dict) -> tuple[dict, dict]:
    """
    Apply user corrections to the saved annotated_blocks and recompute NOI.

    corrections = {
        "total_revenue_row": int | None,
        "total_expense_row": int | None,
        "noi_row":           int | None,
    }

    PERSISTS the corrected annotated_blocks and the new comparison back to
    storage so a page refresh shows the latest state.

    Returns (corrected_entry, comparison_dict).
    """
    annotated = storage.read_json(upload_id, "annotated_blocks.json")
    corrected = apply_corrections(annotated, corrections)
    result    = _recompute_noi(corrected)

    storage.write_json(upload_id, "annotated_blocks.json", corrected)
    storage.write_json(upload_id, "comparison.json",       result["comparison"])

    return corrected, result["comparison"]


def load_annotated_blocks(upload_id) -> dict:
    return storage.read_json(upload_id, "annotated_blocks.json")


def load_comparison(upload_id) -> dict:
    return storage.read_json(upload_id, "comparison.json")


# ═══════════════════════════════════════════════════════════════════════
#  Stage 2 — Mapping (rulebook lookup + AI fallback)
# ═══════════════════════════════════════════════════════════════════════

def run_mapping(upload_id) -> dict:
    """
    Runs the full mapping stage on an already-corrected annotated_blocks entry.

    Steps:
        1. map_results       → auto_mapped.json   (rulebook lookup)
        2. run_ai_mapping    → ai_mapped.json     (AI fallback for not_found rows)
        3. ai_mapping_logs.json — per-row prompt/response audit trail

    Synchronous. Takes 30-180s for a typical T12 depending on how many rows
    fall to the AI fallback (5 workers × ~3s/call).

    Returns the ai_mapped dict so the caller can display a summary.
    Raises any exception from the pipeline directly — caller handles errors.
    """
    import time
    t0 = time.time()
    print(f"[bridge] Stage 2 starting for upload {upload_id}", flush=True)

    rulebook  = _load_latest_rulebook()
    annotated = storage.read_json(upload_id, "annotated_blocks.json")

    print(f"[bridge] Stage 2a — rulebook lookup (map_blocks)", flush=True)
    auto_mapped = map_results(annotated, rulebook)
    storage.write_json(upload_id, "auto_mapped.json", auto_mapped)
    s = auto_mapped["summary"]
    print(f"[bridge]   {s['data_rows']} data rows | {s['mapped']} mapped | {s['unmapped']} unmapped", flush=True)

    print(f"[bridge] Stage 2b — AI fallback (find_mapping)", flush=True)
    ai_mapped, run_logs = run_ai_mapping(auto_mapped, rulebook)
    storage.write_json(upload_id, "ai_mapped.json", ai_mapped)
    if run_logs:
        storage.write_json(upload_id, "ai_mapping_logs.json", run_logs)

    print(f"[bridge] Stage 2 finished in {time.time() - t0:.1f}s", flush=True)
    return ai_mapped


def load_mapped(upload_id) -> dict:
    return storage.read_json(upload_id, "ai_mapped.json")


def save_mapped(upload_id, mapped_data: dict) -> None:
    storage.write_json(upload_id, "ai_mapped.json", mapped_data)


def load_categories() -> list[str]:
    """Returns the sorted canonical category list from the latest rulebook (dropdown options)."""
    return get_rulebook_categories(_load_latest_rulebook())


def load_actual_noi(upload_id) -> dict:
    return storage.read_json(upload_id, "actual_noi.json")
