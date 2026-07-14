"""
t12_mapping/pipeline_bridge.py

The connection between the page views and the t12_pipeline — deliberately THIN:

    load the run-state → run ONE named workflow → save the run-state.

  - The run-state lives in `state.json` (+ `cell_grid.json` as a heavy side artifact).
  - Every workflow is `run(state) -> state` and is named in `stages.STEPS`
    (`stage1_parse`, `stage1_check_anchors`, `stage2_classify`, `stage3_mapping`,
    `stage3_update_mapping`). A view picks a workflow by NAME; it never assembles one.
  - No pipeline logic lives here. The rulebook load, the mapping input adapter and the
    stage composition all live in the pipeline, so every stage is runnable without Django.

The t12_pipeline package is installed in editable mode (`pip install -e ./app/t12_pipeline`).
"""

import json
from pathlib import Path

from shared import storage

from t12_pipeline.config.rulebook_utils import get_rulebook_categories, load_latest_rulebook
from t12_pipeline.pipeline.parsing.cell_grid import extract_cell_grid
from t12_pipeline.pipeline.parsing.preflight import screen_name, screen_structure
from t12_pipeline.pipeline.parsing import stages


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
    # cell_grid (heavy) and feedback (holds a pydantic diagnosis; the clean summary lives in
    # classification.diagnosis) are kept out of the persisted state.
    skip = ("cell_grid", "feedback")
    storage.write_json(run_id, "state.json", {k: v for k, v in state.items() if k not in skip})


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


def _restore_cell_grid(cg: dict) -> dict:
    """Restore integer column keys after a JSON round-trip."""
    for row in cg["rows"]:
        row["cells"] = {int(k): v for k, v in row["cells"].items()}
    return cg


def run_preflight(xlsx_local_path) -> dict:
    """STAGE 0 — screen the workbook before any parsing or AI call (pre-run: no run-state
    yet, a rejected file is never accepted). Checks the name first (rent roll / Model-T12)
    so those never even get read; otherwise reads the grid once for the structural check.
    Returns {ok, kind, reason}."""
    name_reject = screen_name(Path(xlsx_local_path).name)
    if name_reject:
        return name_reject
    return screen_structure(extract_cell_grid(str(xlsx_local_path)))


# Every page reads the run-state directly via get_state — no per-page loader needed.


def load_categories() -> list[str]:
    """Returns the sorted canonical category list from the latest rulebook (dropdown options)."""
    return get_rulebook_categories(load_latest_rulebook())
