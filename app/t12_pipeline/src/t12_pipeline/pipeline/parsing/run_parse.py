"""One-shot convenience runner — run both stages in one pass and flatten the run-state.

The stage logic lives in `stages.py` (each pipeline module exposes a `run(state)` step;
`stages` composes them). `parse_file` drives `stage1` + `classify` over an in-memory run-state
and flattens the result to a flat dict — handy for tests and scripts that want to run the whole
pipeline on a file. The app never calls this; it runs the stages through the bridge's `run_step`,
stage by stage.
"""
from pathlib import Path

from .stages import stage1, classify


def parse_file(xlsx_path, *, run_feedback=True, max_iters=5):
    """Stage 1 + Stage 2 in one pass; returns a flat result dict (for tests / scripts)."""
    state = stage1({"file": {"name": Path(xlsx_path).name, "path": str(xlsx_path)}})
    state = classify({**state, "run_feedback": run_feedback, "max_iters": max_iters})
    cls = state["classification"]
    return {
        "format":              state["format"]["format"],
        "format_result":       state["format"],
        "final_map":           state["structure_map"],
        "sub_results":         state["sub_results"],
        "structure_map":       state["structure_map_ai"],
        "cell_grid":           state["cell_grid"],
        "anchor_rows":         state["anchor_rows"],
        "anchor_lock":         state["anchor_lock"],
        "classified":          cls["classified"],
        "noi":                 cls["noi"],
        "feedback":            state.get("feedback"),
        "signal_rows":         state["signals"],
        "low_confidence_rows": cls["low_confidence_rows"],
    }
