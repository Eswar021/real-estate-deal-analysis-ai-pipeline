"""The step catalog and the composite stages, all in run-state form (`run(state) -> state`).

Every pipeline module now exposes its own `run(state)` step (see each module). This file
composes them into the two coherent stages the app runs, and publishes `STEPS` — the registry
the bridge's `run_step` dispatches on and the views sequence.

  stage1  = extract_grid → detect_format → resolve_columns → extract_anchor_rows → lock_anchors
  classify = (apply confirmed anchors) → extract_signals → classify → sections → verify_noi
             → [NOI fail? → diagnose → apply_fix → re-verify (loop)] → flag_low_confidence

Every fork here is owned by the FLOW (decided by the data / the arithmetic), never by a caller
flag — a caller can only re-enter a step, not switch part of it off.

See docs/build/RESTRUCTURE_PLAN.md.
"""
from . import cell_grid, format_detect, structure_map, extract, anchor_lock, sections, noi, feedback
from . import classify as classify_mod
from . import parse_log
from .legacy_adapter import column_headers


def stage1(state):
    """STAGE 1 — up to the R − E = NOI anchor lock. reads: file. writes: cell_grid, format,
    structure_map, structure_map_ai, sub_results, anchor_rows, anchor_lock."""
    state = cell_grid.run(state)           # extract_grid
    state = format_detect.run(state)       # detect_format
    state = structure_map.run(state)       # resolve_columns (template / AI)
    state = extract.run_anchor_rows(state)  # light {row, description, values}
    state = anchor_lock.run(state)         # R − E = NOI lock
    parse_log.stage1(state)
    return {**state, "step": "locked"}


def check_anchors(state):
    """Light re-verify of state['anchors'] — delegates to the anchor_lock step."""
    return anchor_lock.run_check(state)


def _apply_confirmed_anchors(state):
    """Fold the user's confirmed R/E/NOI picks into structure_map (keeping the auto-detected
    expense split only if the expense row is unchanged) and flip the lock to MANUAL — the
    user has now confirmed the anchors, so the run-state carries that status directly."""
    picks = state.get("anchors")
    if picks is None:
        return state
    fm = dict(state["structure_map"])
    locked_exp, locked_split = fm.get("expense_end_row"), fm.get("expense_split_rows")
    fm["revenue_end_row"] = picks.get("revenue_end_row")
    fm["expense_end_row"] = picks.get("expense_end_row")
    fm["noi_row"]         = picks.get("noi_row")
    fm["expense_split_rows"] = locked_split if picks.get("expense_end_row") == locked_exp else None
    lock = {**(state.get("anchor_lock") or {}), "status": "MANUAL", "method": "manual",
            "anchors": {"revenue_end_row": fm["revenue_end_row"],
                        "expense_end_row": fm["expense_end_row"], "noi_row": fm["noi_row"]}}
    return {**state, "structure_map": fm, "anchor_lock": lock}


def classify(state):
    """STAGE 2 — apply the confirmed anchors, then extract signals → classify + fact override
    → sections → verify_noi → (on FAIL: diagnose → apply_fix → re-verify) → confidence flags.
    The NOI-fail fork belongs to the graph: callers just re-enter this step and it decides.
    reads: cell_grid, structure_map, anchors. writes: structure_map (anchors applied), signals,
    classification."""
    state = _apply_confirmed_anchors(state)
    state = extract.run_signals(state)
    parse_log.stage2_start(state)
    state = classify_mod.run(state)        # derive subsections + classify + override
    state = sections.run(state)
    state = noi.run(state)
    parse_log.stage2_classify(state)
    parse_log.stage2_noi(state, "initial")
    # The GRAPH owns this fork — there is deliberately no caller flag to switch it off (one used
    # to exist and let a re-classify silently drop the AI's corrections). NOI failing IS the
    # trigger: diagnose → apply_fix → re-verify, and a fix is kept only if the money reconciles.
    if not state["noi"]["overall_pass"] and state["structure_map"].get("noi_row"):
        state = feedback.run(state)        # diagnose → apply_fix → re-verify (arithmetic-gated)
        parse_log.stage2_classify(state)   # the CORRECTED classification
        parse_log.stage2_noi(state, "final")
    state = classify_mod.run_flag(state)
    parse_log.stage2_end(state)

    # Extract a JSON-clean diagnosis summary (the raw feedback holds a pydantic object that
    # doesn't survive the state.json round-trip). column_headers computed here (we have the
    # grid) so the review page never needs the heavy cell_grid.
    fb, diagnosis = state.get("feedback"), None
    if fb:
        dg = fb.get("diagnosis")
        diagnosis = {"status":             fb.get("status"),
                     "iterations":         fb.get("iterations"),
                     "user_message":       getattr(dg, "user_message", None) if dg else None,
                     "data_inconsistency": getattr(dg, "data_inconsistency", None) if dg else None}

    classification = {"classified":           state["classified"],
                      "noi":                  state["noi"],
                      "diagnosis":            diagnosis,
                      "low_confidence_rows":  state["low_confidence_rows"],
                      "column_headers":       column_headers({"final_map": state["structure_map"],
                                                              "cell_grid": state["cell_grid"]}),
                      "confidence_threshold": classify_mod.LOW_CONFIDENCE_MARGIN}
    # `feedback` (the raw loop result, with a pydantic diagnosis) is left top-level for the
    # CLI report only; save_state strips it from state.json (the clean summary is in
    # classification.diagnosis). classified/noi/low_confidence_rows fold into classification.
    keep = {k: v for k, v in state.items()
            if k not in ("classified", "noi", "low_confidence_rows")}
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
