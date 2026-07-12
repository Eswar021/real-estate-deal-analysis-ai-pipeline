"""The step catalog and the composite stages, all in run-state form (`run(state) -> state`).

Every pipeline module now exposes its own `run(state)` step (see each module). This file
composes them into the two coherent stages the app runs, and publishes `STEPS` — the registry
the bridge's `run_step` dispatches on and the views sequence.

  stage1  = extract_grid → detect_format → resolve_columns → extract_anchor_rows → lock_anchors
  classify = (apply confirmed anchors) → extract_signals → classify → sections → verify_noi
             → (diagnose, only on NOI fail) → flag_low_confidence

See docs/build/RESTRUCTURE_PLAN.md.
"""
from . import cell_grid, format_detect, structure_map, extract, anchor_lock, sections, noi, feedback
from . import classify as classify_mod


def stage1(state):
    """STAGE 1 — up to the R − E = NOI anchor lock. reads: file. writes: cell_grid, format,
    structure_map, structure_map_ai, sub_results, anchor_rows, anchor_lock."""
    state = cell_grid.run(state)           # extract_grid
    state = format_detect.run(state)       # detect_format
    state = structure_map.run(state)       # resolve_columns (template / AI)
    state = extract.run_anchor_rows(state)  # light {row, description, values}
    state = anchor_lock.run(state)         # R − E = NOI lock
    return {**state, "step": "locked"}


def check_anchors(state):
    """Light re-verify of state['anchors'] — delegates to the anchor_lock step."""
    return anchor_lock.run_check(state)


def _apply_confirmed_anchors(state):
    """Fold the user's confirmed R/E/NOI picks into structure_map, keeping the auto-detected
    expense split only if the expense row is unchanged from the pre-filled one."""
    picks = state.get("anchors")
    if picks is None:
        return state
    fm = dict(state["structure_map"])
    locked_exp, locked_split = fm.get("expense_end_row"), fm.get("expense_split_rows")
    fm["revenue_end_row"] = picks.get("revenue_end_row")
    fm["expense_end_row"] = picks.get("expense_end_row")
    fm["noi_row"]         = picks.get("noi_row")
    fm["expense_split_rows"] = locked_split if picks.get("expense_end_row") == locked_exp else None
    return {**state, "structure_map": fm}


def classify(state):
    """STAGE 2 — apply the confirmed anchors, then extract signals → classify + fact override
    → sections → NOI verify → (AI diagnosis only on NOI fail) → confidence flags.
    reads: cell_grid, structure_map, anchors, run_feedback?, max_iters?.
    writes: structure_map (anchors applied), signals, classification."""
    state = _apply_confirmed_anchors(state)
    state = extract.run_signals(state)
    state = classify_mod.run(state)        # derive subsections + classify + override
    state = sections.run(state)
    state = noi.run(state)
    if not state["noi"]["overall_pass"] and state.get("run_feedback", True) \
            and state["structure_map"].get("noi_row"):
        state = feedback.run(state)        # AI diagnosis loop
    state = classify_mod.run_flag(state)

    classification = {"classified":          state["classified"],
                      "noi":                 state["noi"],
                      "feedback":            state.get("feedback"),
                      "low_confidence_rows": state["low_confidence_rows"]}
    keep = {k: v for k, v in state.items()
            if k not in ("classified", "noi", "feedback", "low_confidence_rows")}
    return {**keep, "classification": classification, "step": "classified"}


# The step registry: composite stages + the individual steps (available for finer routing).
STEPS = {
    "stage1":          stage1,
    "classify":        classify,
    "check_anchors":   check_anchors,
    "extract_grid":    cell_grid.run,
    "detect_format":   format_detect.run,
    "resolve_columns": structure_map.run,
    "anchor_rows":     extract.run_anchor_rows,
    "lock_anchors":    anchor_lock.run,
    "signals":         extract.run_signals,
    "classify_rows":   classify_mod.run,
    "sections":        sections.run,
    "verify_noi":      noi.run,
    "diagnose":        feedback.run,
    "flag":            classify_mod.run_flag,
}
