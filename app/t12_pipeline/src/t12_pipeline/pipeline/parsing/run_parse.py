"""One-shot convenience runner — run both stages in one pass and flatten the run-state.

The stage logic lives in `stages.py` (each pipeline module exposes a `run(state)` step;
`stages` composes them). `parse_file` drives `stage1` + `classify` over an in-memory run-state
and flattens the result to a flat dict — handy for tests and scripts that want to run the whole
pipeline on a file. The app never calls this; it runs the stages through the bridge's `run_step`,
stage by stage.
"""
from pathlib import Path

from t12_pipeline.config.log_config import configure_logging
from .stages import stage1, classify


def parse_file(xlsx_path):
    """Stage 1 + Stage 2 in one pass; returns a flat result dict (for tests / scripts).

    Runs the REAL graph — there is no 'skip the AI' flag (that escape hatch is what let a
    re-classify silently drop the diagnosis's corrections). A test that must not hit the AI
    mocks `feedback.run_diagnosis_agent`, the same way it already mocks `run_structure_agent`."""
    configure_logging()   # so CLI/test runs log to the same file as the UI
    state = stage1({"file": {"name": Path(xlsx_path).name, "path": str(xlsx_path)}})
    state = classify(state)
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
