"""
pipeline_bridge/t12.py

Thin wrapper that calls the t12_pipeline detection functions and
saves each stage output to the upload's pipeline directory.

Adds T12_PIPELINE_SRC (and its 1_detection subdirectory) to sys.path
so the pipeline modules can be imported directly without installation.
"""

import json
import sys
from pathlib import Path

from django.conf import settings

_SRC = Path(settings.T12_PIPELINE_SRC)
_DETECTION_DIR = _SRC / "pipeline" / "1_detection"

for _p in [str(_SRC), str(_DETECTION_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from detect_blocks import classify_file
from annotate_totals import annotate_file
from compute_noi import compute_noi, extract_actual_noi
from compare_noi import compare
from corrections import apply_corrections, recompute_noi as _recompute_noi


def run_detection(xlsx_path: Path, pipeline_dir: Path) -> dict:
    """
    Runs the full detection stage on a single Excel file.

    Steps:
        1. classify_file  → block_detection.json
        2. annotate_file  → annotated_blocks.json
        3. extract_actual_noi + compute_noi → actual_noi.json, computed_noi.json
        4. compare        → comparison.json

    Returns the comparison dict so the view can display PASS/FAIL and totals.
    Raises any exception from the pipeline directly — caller handles errors.
    """
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1a: detect + classify every row
    detection = classify_file(str(xlsx_path))
    _write(pipeline_dir / "block_detection.json", detection)

    # Stage 1b: stamp is_total_revenue / is_total_expense / is_noi flags
    annotated = annotate_file(detection)
    _write(pipeline_dir / "annotated_blocks.json", annotated)

    # Stage 1c: extract vendor NOI and compute row-method NOI
    actual   = extract_actual_noi(annotated)
    computed = compute_noi(annotated)
    _write(pipeline_dir / "actual_noi.json",   actual)
    _write(pipeline_dir / "computed_noi.json", computed)

    # Stage 1d: compare actual vs computed, produce PASS/FAIL per month
    comparison = compare(actual, computed)
    _write(pipeline_dir / "comparison.json", comparison)

    return comparison


def apply_and_recompute(pipeline_dir: Path, corrections: dict) -> tuple[dict, dict]:
    """
    Apply user corrections to the saved annotated_blocks and recompute NOI.

    corrections = {
        "total_revenue_row": int | None,
        "total_expense_row": int | None,
        "noi_row":           int | None,
    }

    Returns (corrected_entry, comparison_dict).
    Does NOT overwrite the saved annotated_blocks.json — corrections live only in memory
    until the user explicitly saves.
    """
    annotated = load_annotated_blocks(pipeline_dir)
    corrected = apply_corrections(annotated, corrections)
    result    = _recompute_noi(corrected)
    return corrected, result["comparison"]


def load_annotated_blocks(pipeline_dir: Path) -> dict:
    """Load a previously saved annotated_blocks JSON from the pipeline dir."""
    path = pipeline_dir / "annotated_blocks.json"
    with open(path) as f:
        return json.load(f)


def load_comparison(pipeline_dir: Path) -> dict:
    """Load a previously saved comparison JSON from the pipeline dir."""
    path = pipeline_dir / "comparison.json"
    with open(path) as f:
        return json.load(f)


def _write(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
