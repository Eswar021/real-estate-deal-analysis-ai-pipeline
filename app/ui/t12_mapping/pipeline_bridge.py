"""
t12_mapping/pipeline_bridge.py

The connection between the page views and the t12_pipeline. It runs the pipeline STAGE BY
STAGE against a single accumulating run-state (one per upload_id), mirroring the app flow —
nothing downstream fires until the user submits.

Restructure (Phase A, see app/t12_pipeline/docs/build/RESTRUCTURE_PLAN.md):
  - The run-state lives in `state.json` (+ `cell_grid.json` as a heavy side artifact).
  - Every pipeline step is `run(state) -> state` (see pipeline.parsing.stages).
  - `run_step(id, name, **inputs)` = load state → run the named step → save state.
  - The stage entry points below still ALSO write the current per-page files
    (anchor_lock / parse_state / classification / annotated_blocks / comparison /
    actual_noi) so the existing pages keep working while the migration proceeds.

The t12_pipeline package is installed in editable mode (`pip install -e ./app/t12_pipeline`).
"""

import json
from pathlib import Path

from shared import storage

from t12_pipeline.config.paths import DB_RULEBOOKS_DIR
from t12_pipeline.config.rulebook_utils import get_rulebook_categories
from t12_pipeline.pipeline.parsing.cell_grid import extract_cell_grid
from t12_pipeline.pipeline.parsing.preflight import screen_name, screen_structure
from t12_pipeline.pipeline.parsing import stages
from t12_pipeline.pipeline.parsing import legacy_adapter as la
from t12_pipeline.pipeline.parsing.presenter import build_classification_view
from t12_pipeline.pipeline.mapping.map_blocks import map_results
from t12_pipeline.pipeline.mapping.find_mapping import run_ai_mapping


# ── run-state: one accumulating dict per upload_id, persisted as state.json ──────────
#    The step catalog (stages.STEPS) lives in the pipeline; cell_grid is stored separately
#    (cell_grid.json) — it's multi-MB, kept out of state.json.

def get_state(run_id, with_grid: bool = True) -> dict:
    """Load the run-state; inject the cell_grid side artifact unless the caller won't need it."""
    state = storage.read_json(run_id, "state.json")
    if with_grid:
        try:
            state["cell_grid"] = _restore_cell_grid(storage.read_json(run_id, "cell_grid.json"))
        except FileNotFoundError:
            pass
    return state


def save_state(run_id, state: dict) -> None:
    """Persist the run-state to state.json. The heavy cell_grid is a read-mostly side
    artifact — written once (the first save that carries it) and skipped thereafter, since
    it never changes after extraction."""
    grid = state.get("cell_grid")
    if grid is not None and not storage.exists(run_id, "cell_grid.json"):
        storage.write_json(run_id, "cell_grid.json", grid)
    storage.write_json(run_id, "state.json", {k: v for k, v in state.items() if k != "cell_grid"})


def run_step(run_id, name, *, save: bool = True, with_grid: bool = True, **inputs) -> dict:
    """load state → merge inputs → run the named `run(state)` step → (save) → return state."""
    try:
        state = get_state(run_id, with_grid=with_grid)
    except FileNotFoundError:
        state = {"run_id": str(run_id)}
    state.update(inputs)
    state = stages.STEPS[name](state)
    if save:
        save_state(run_id, state)
    return state


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


def _res_from_state(state, anchor_lock) -> dict:
    """The flat `res` shape the presenter / legacy_adapter consume, built from state slices."""
    cls = state["classification"]
    return {"format": state["format"]["format"], "final_map": state["structure_map"],
            "cell_grid": state["cell_grid"], "anchor_lock": anchor_lock,
            "classified": cls["classified"], "noi": cls["noi"], "feedback": cls["feedback"],
            "signal_rows": state["signals"], "low_confidence_rows": cls["low_confidence_rows"]}


def run_preflight(xlsx_local_path) -> dict:
    """STAGE 0 — screen the workbook before any parsing or AI call (pre-run: no run-state
    yet, a rejected file is never accepted). Checks the name first (rent roll / Model-T12)
    so those never even get read; otherwise reads the grid once for the structural check.
    Returns {ok, kind, reason}."""
    name_reject = screen_name(Path(xlsx_local_path).name)
    if name_reject:
        return name_reject
    return screen_structure(extract_cell_grid(str(xlsx_local_path)))


# ── mirror helpers: write the run-state to the current per-page files ─────────────────
#    Transitional (Phase C). Phase D drops these once every page reads the run-state directly.

def mirror_stage1(upload_id, state) -> None:
    """Mirror the Stage-1 run-state to the files the anchor gate reads (anchor_lock +
    parse_state). cell_grid.json is written by save_state on the first save."""
    storage.write_json(upload_id, "anchor_lock.json", state["anchor_lock"])
    storage.write_json(upload_id, "parse_state.json",
                       {"file": state["file"]["name"], "format": state["format"]["format"],
                        "final_map": state["structure_map"], "anchor_rows": state["anchor_rows"]})


def mirror_stage2(upload_id, state) -> dict:
    """Mirror the Stage-2 run-state to the per-page files (classification / annotated_blocks /
    comparison / actual_noi) and flip the lock to MANUAL (the user confirmed the anchors).
    Returns the comparison."""
    fm = state["structure_map"]
    anchor_lock = {**state["anchor_lock"], "status": "MANUAL", "method": "manual",
                   "anchors": {"revenue_end_row": fm["revenue_end_row"],
                               "expense_end_row": fm["expense_end_row"],
                               "noi_row":         fm["noi_row"]}}
    storage.write_json(upload_id, "anchor_lock.json", anchor_lock)

    res = _res_from_state(state, anchor_lock)
    comparison = la.to_comparison(res, state["file"]["name"])
    storage.write_json(upload_id, "classification.json", build_classification_view(res, state["file"]["name"]))
    storage.write_json(upload_id, "annotated_blocks.json", la.to_annotated(res, state["file"]["name"]))
    storage.write_json(upload_id, "comparison.json",       comparison)
    storage.write_json(upload_id, "actual_noi.json",       la.to_actual_noi(res))
    return comparison


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
