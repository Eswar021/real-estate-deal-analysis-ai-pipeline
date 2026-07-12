"""
t12_mapping/pipeline_bridge.py

Thin wrapper that runs the t12_pipeline anchor-first parser AND the mapping stage,
persisting each stage output via the storage abstraction (dev=local FS, prod=S3).

The parse runs STAGE BY STAGE, mirroring the app flow (nothing downstream fires until
the user submits):

  run_detection      — STAGE 1: format detect → resolve columns → anchor lock
                       (R − E = NOI). Stops here. NO classification.
  run_classification — STAGE 2: classify + fact override → section → NOI verify.
                       Runs only after the user confirms the anchors at the gate
                       (every file stops at the gate — nothing auto-advances).

The one-pass `run_parse.parse_file` is for the CLI report / testing only; the app never
calls it. Stage-2 output is mapped to the legacy annotated_blocks / comparison shapes via
legacy_adapter, so the UI pages and the mapping stage are unchanged.

The t12_pipeline package is installed in editable mode (`pip install -e ./app/t12_pipeline`).
"""

import json
from pathlib import Path

from shared import storage

from t12_pipeline.config.paths import DB_RULEBOOKS_DIR
from t12_pipeline.config.rulebook_utils import get_rulebook_categories
from t12_pipeline.pipeline.parsing.cell_grid import extract_cell_grid
from t12_pipeline.pipeline.parsing.preflight import screen_name, screen_structure
from t12_pipeline.pipeline.parsing.run_parse import parse_to_anchors, classify_within_anchors
from t12_pipeline.pipeline.parsing.anchor_lock import reconcile_triple
from t12_pipeline.pipeline.parsing import legacy_adapter as la
from t12_pipeline.pipeline.parsing.presenter import build_classification_view
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


def _persist_stage1(upload_id, s1, file_name) -> None:
    """Write the Stage-1 state the anchor gate reads + Stage 2 reuses (no AI re-call):
    anchor_lock (status/candidates/passing), parse_state (format + final_map + the light
    anchor_rows for the gate to render), and the cell_grid. NO signals, NO classification
    yet — Stage 2 extracts the full signal vector from the cell_grid on confirm."""
    storage.write_json(upload_id, "anchor_lock.json", s1["anchor_lock"])
    storage.write_json(upload_id, "parse_state.json",
                       {"file": file_name, "format": s1["format"],
                        "final_map": s1["final_map"], "anchor_rows": s1["anchor_rows"]})
    storage.write_json(upload_id, "cell_grid.json", s1["cell_grid"])


def _persist_stage2(upload_id, res, file_name) -> dict:
    """Write the Stage-2 outputs. `classification.json` is the natural view the review page
    reads directly (thin bridge — the pipeline's presenter builds it, we just forward it).
    The legacy annotated_blocks / comparison / actual_noi are still written for the mapping
    stage and the current NOI helpers. Returns the comparison."""
    comparison = la.to_comparison(res, file_name)
    storage.write_json(upload_id, "classification.json", build_classification_view(res, file_name))
    storage.write_json(upload_id, "annotated_blocks.json", la.to_annotated(res, file_name))
    storage.write_json(upload_id, "comparison.json",       comparison)
    storage.write_json(upload_id, "actual_noi.json",       la.to_actual_noi(res))
    return comparison


def run_preflight(xlsx_local_path) -> dict:
    """STAGE 0 — screen the workbook before any parsing or AI call. Checks the name first
    (rent roll / Model-T12) so those never even get read; otherwise reads the grid once for
    the structural check. Returns {ok, kind, reason}."""
    name_reject = screen_name(Path(xlsx_local_path).name)
    if name_reject:
        return name_reject
    return screen_structure(extract_cell_grid(str(xlsx_local_path)))


def run_detection(upload_id, xlsx_local_path) -> dict:
    """STAGE 1 — anchor-first parse up to the R − E = NOI lock: format detect → resolve
    columns (template / AI structure agent) → dynamic extract → anchor lock. STOPS here;
    classification runs only after the user confirms the anchors. Persists the Stage-1
    state (anchor_lock, parse_state, cell_grid) and returns the anchor_lock. Every file
    then goes to the anchor gate — the status only pre-fills it, it never auto-advances."""
    s1 = parse_to_anchors(str(xlsx_local_path))
    _persist_stage1(upload_id, s1, Path(xlsx_local_path).name)
    return s1["anchor_lock"]


def run_classification(upload_id, anchors: dict, *, run_feedback: bool) -> dict:
    """STAGE 2 — classify inside the confirmed anchors → section → NOI verify → (diagnosis).
    Reuses the Stage-1 parse_state + cell_grid; the AI structure agent is NOT re-called.

    anchors = {"revenue_end_row", "expense_end_row", "noi_row"} — the user's confirmed rows.
    Overrides the anchors, marks the lock MANUAL, and preserves the auto-detected expense
    split only if the user kept the pre-filled expense row.

    run_feedback=True runs the AI failure-diagnosis loop when NOI fails (the gate Confirm);
    run_feedback=False is a deterministic recompute with no AI (the review-page recompute).

    Persists classification.json + annotated_blocks / comparison / actual_noi. Returns the
    comparison dict."""
    state = storage.read_json(upload_id, "parse_state.json")
    cell_grid = _restore_cell_grid(storage.read_json(upload_id, "cell_grid.json"))
    final_map = dict(state["final_map"])
    locked_exp   = final_map.get("expense_end_row")
    locked_split = final_map.get("expense_split_rows")
    final_map["revenue_end_row"] = anchors.get("revenue_end_row")
    final_map["expense_end_row"] = anchors.get("expense_end_row")
    final_map["noi_row"]         = anchors.get("noi_row")
    # keep the auto-detected expense split only if the user left the expense row on the
    # pre-filled (locked) one; picking a different single row drops the split.
    final_map["expense_split_rows"] = (
        locked_split if anchors.get("expense_end_row") == locked_exp else None)

    # Stage 2 extracts the full signal vector from the cell_grid here (not at upload).
    s2 = classify_within_anchors(cell_grid, final_map, run_feedback=run_feedback)

    anchor_lock = storage.read_json(upload_id, "anchor_lock.json")
    anchor_lock = {**anchor_lock, "status": "MANUAL", "method": "manual",
                   "anchors": {"revenue_end_row": final_map["revenue_end_row"],
                               "expense_end_row": final_map["expense_end_row"],
                               "noi_row":         final_map["noi_row"]}}
    storage.write_json(upload_id, "anchor_lock.json", anchor_lock)

    res = {"format": state["format"], "final_map": final_map, "cell_grid": cell_grid,
           "anchor_lock": anchor_lock, **s2}
    comparison = _persist_stage2(upload_id, res, state.get("file", ""))
    storage.write_json(upload_id, "parse_state.json", {**state, "final_map": final_map})
    return comparison


def check_anchors(upload_id, anchors: dict) -> dict:
    """Anchor-gate RE-VERIFY — light `R − |E| = NOI` check on the picked rows using only
    the Stage-1 anchor_rows. NO classification, NO AI, nothing persisted. Preserves the
    auto-detected expense split only if the user kept the pre-filled expense row.
    Returns the reconcile_triple result ({reconciles, matched, months})."""
    state = storage.read_json(upload_id, "parse_state.json")
    lock  = storage.read_json(upload_id, "anchor_lock.json")
    locked = lock.get("anchors") or {}
    exp = anchors.get("expense_end_row")
    split = locked.get("expense_split_rows") if exp == locked.get("expense_end_row") else None
    expense_unit = split or [exp]
    return reconcile_triple(state.get("anchor_rows", []),
                            anchors.get("revenue_end_row"), expense_unit, anchors.get("noi_row"))


def confirm_anchors(upload_id, anchors: dict) -> tuple[dict, dict]:
    """Anchor-gate CONFIRM — commit the 3 anchors and run Stage 2 WITH the AI failure-
    diagnosis loop (fires only if NOI fails). Returns (classification_view, comparison)."""
    comparison = run_classification(upload_id, {
        "revenue_end_row": anchors.get("revenue_end_row"),
        "expense_end_row": anchors.get("expense_end_row"),
        "noi_row":         anchors.get("noi_row"),
    }, run_feedback=True)
    return storage.read_json(upload_id, "classification.json"), comparison


def apply_and_recompute(upload_id, corrections: dict) -> tuple[dict, dict]:
    """Review-page RECOMPUTE — re-run Stage 2 on adjusted anchors, deterministically (no
    AI). corrections = {"total_revenue_row", "total_expense_row", "noi_row"}.
    Returns (classification_view, comparison)."""
    comparison = run_classification(upload_id, {
        "revenue_end_row": corrections.get("total_revenue_row"),
        "expense_end_row": corrections.get("total_expense_row"),
        "noi_row":         corrections.get("noi_row"),
    }, run_feedback=False)
    return storage.read_json(upload_id, "classification.json"), comparison


def load_annotated_blocks(upload_id) -> dict:
    return storage.read_json(upload_id, "annotated_blocks.json")


def load_comparison(upload_id) -> dict:
    return storage.read_json(upload_id, "comparison.json")


def load_anchor_lock(upload_id) -> dict:
    return storage.read_json(upload_id, "anchor_lock.json")


def load_classification(upload_id) -> dict:
    """Stage-2 natural view — anchors, NOI verification, and every classified row
    (class/section/values/confidence/low_confidence). The review page reads this directly."""
    return storage.read_json(upload_id, "classification.json")


def load_parse_state(upload_id) -> dict:
    """Stage-1 state — {file, format, final_map, anchor_rows}. The anchor gate reads
    anchor_rows (the light {row, description, values} build) to render the candidate/
    all-row selectors before Stage 2 has extracted signals or produced annotated_blocks."""
    return storage.read_json(upload_id, "parse_state.json")


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
