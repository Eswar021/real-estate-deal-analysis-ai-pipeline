"""
t12_mapping/pipeline_bridge.py

Thin wrapper that calls the t12_pipeline detection functions and persists
each stage output via the storage abstraction (so dev=local FS, prod=S3
is a one-line settings change).

The t12_pipeline package is installed in editable mode
(`pip install -e ./app/t12_pipeline`) — no sys.path manipulation needed.
"""

from shared import storage

from t12_pipeline.pipeline.detection.detect_blocks import classify_file
from t12_pipeline.pipeline.detection.annotate_totals import annotate_file
from t12_pipeline.pipeline.detection.compute_noi import compute_noi, extract_actual_noi
from t12_pipeline.pipeline.detection.compare_noi import compare
from t12_pipeline.pipeline.detection.corrections import (
    apply_corrections,
    recompute_noi as _recompute_noi,
)


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
