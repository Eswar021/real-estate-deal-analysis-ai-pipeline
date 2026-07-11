"""
t12_mapping/pipeline_bridge.py

Thin wrapper that runs the t12_pipeline anchor-first parser AND the mapping stage,
persisting each stage output via the storage abstraction (dev=local FS, prod=S3).

Detection is now the anchor-first pipeline (pipeline/parsing/run_parse.parse_file);
its result is mapped to the legacy annotated_blocks / comparison shapes via
legacy_adapter, so the UI pages and the mapping stage (Stage 3) are unchanged.
`apply_and_recompute` doubles as the anchor-confirmation step (the user sets the
revenue / expense / NOI rows), re-classifying without re-calling the AI.

The t12_pipeline package is installed in editable mode (`pip install -e ./app/t12_pipeline`).
"""

import json
from pathlib import Path

from shared import storage

from t12_pipeline.config.paths import DB_RULEBOOKS_DIR
from t12_pipeline.config.rulebook_utils import get_rulebook_categories
from t12_pipeline.pipeline.parsing.run_parse import parse_file
from t12_pipeline.pipeline.parsing.extract import extract_row_signals_dynamic  # noqa: F401 (kept for parity)
from t12_pipeline.pipeline.parsing.anchor_lock import apply_anchor_overrides
from t12_pipeline.pipeline.parsing.classify import classify_rows
from t12_pipeline.pipeline.parsing.sections import assign_sections
from t12_pipeline.pipeline.parsing.noi import verify_noi
from t12_pipeline.pipeline.parsing import legacy_adapter as la
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


def _restore_cell_grid(cg: dict) -> dict:
    """Restore integer column keys after a JSON round-trip."""
    for row in cg["rows"]:
        row["cells"] = {int(k): v for k, v in row["cells"].items()}
    return cg


def _persist(upload_id, res, file_name) -> dict:
    """Write the legacy-shaped stage files (for the UI + mapping) plus the anchor-first
    state (for re-classification without re-running the AI). Returns the comparison."""
    comparison = la.to_comparison(res, file_name)
    storage.write_json(upload_id, "annotated_blocks.json", la.to_annotated(res, file_name))
    storage.write_json(upload_id, "comparison.json",       comparison)
    storage.write_json(upload_id, "actual_noi.json",       la.to_actual_noi(res))
    storage.write_json(upload_id, "anchor_lock.json",      res["anchor_lock"])
    storage.write_json(upload_id, "parse_state.json",
                       {"format": res["format"], "final_map": res["final_map"],
                        "signal_rows": res["signal_rows"]})
    storage.write_json(upload_id, "cell_grid.json", res["cell_grid"])
    return comparison


def run_detection(upload_id, xlsx_local_path) -> dict:
    """Anchor-first parse of one Excel file: format detect → resolve columns → extract
    → anchor lock → classify + override → section → NOI verify → (diagnosis loop on
    fail). Persists the legacy stage files + anchor-first state. Returns the comparison
    dict so the view can show PASS/FAIL, totals, and the anchor status."""
    res = parse_file(str(xlsx_local_path))
    return _persist(upload_id, res, Path(xlsx_local_path).name)


def apply_and_recompute(upload_id, corrections: dict) -> tuple[dict, dict]:
    """Confirm/override the R / E / NOI anchors and re-classify + re-verify — WITHOUT
    re-running the AI (reuses the saved structure map + signal rows).

    corrections = {"total_revenue_row": int|None, "total_expense_row": int|None,
                   "noi_row": int|None}

    Persists the corrected annotated_blocks + comparison. Returns (annotated, comparison).
    """
    state = storage.read_json(upload_id, "parse_state.json")
    cell_grid = _restore_cell_grid(storage.read_json(upload_id, "cell_grid.json"))
    final_map = dict(state["final_map"])
    final_map["revenue_end_row"] = corrections.get("total_revenue_row")
    final_map["expense_end_row"] = corrections.get("total_expense_row")
    final_map["noi_row"]         = corrections.get("noi_row")

    classified = apply_anchor_overrides(classify_rows(state["signal_rows"], final_map), final_map)
    assign_sections(classified, final_map)
    noi = verify_noi(classified, cell_grid, final_map)

    res = {"format": state["format"], "final_map": final_map, "classified": classified,
           "noi": noi, "cell_grid": cell_grid,
           "anchor_lock": {"status": "MANUAL", "method": "manual",
                           "anchors": {"revenue_end_row": final_map["revenue_end_row"],
                                       "expense_end_row": final_map["expense_end_row"],
                                       "noi_row": final_map["noi_row"]}}}
    file_name = storage.read_json(upload_id, "comparison.json").get("file", "")
    annotated = la.to_annotated(res, file_name)
    comparison = la.to_comparison(res, file_name)
    storage.write_json(upload_id, "annotated_blocks.json", annotated)
    storage.write_json(upload_id, "comparison.json",       comparison)
    storage.write_json(upload_id, "parse_state.json", {**state, "final_map": final_map})
    return annotated, comparison


# Alias for the new UI naming — same action (set the 3 anchors, re-verify).
def confirm_anchors(upload_id, anchors: dict) -> tuple[dict, dict]:
    return apply_and_recompute(upload_id, {
        "total_revenue_row": anchors.get("revenue_end_row"),
        "total_expense_row": anchors.get("expense_end_row"),
        "noi_row":           anchors.get("noi_row"),
    })


def load_annotated_blocks(upload_id) -> dict:
    return storage.read_json(upload_id, "annotated_blocks.json")


def load_comparison(upload_id) -> dict:
    return storage.read_json(upload_id, "comparison.json")


def load_anchor_lock(upload_id) -> dict:
    return storage.read_json(upload_id, "anchor_lock.json")


# ═══════════════════════════════════════════════════════════════════════
#  Stage 2 — Mapping (rulebook lookup + AI fallback)  — UNCHANGED
# ═══════════════════════════════════════════════════════════════════════

def run_mapping(upload_id) -> dict:
    """Runs the full mapping stage on the (corrected) annotated_blocks entry.
    Synchronous; 30-180s depending on how many rows fall to the AI fallback."""
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
