"""Stage functions in run-state form: every one is `run(state) -> state`.

These are the units the bridge's `run_step` executes and the views sequence. Each reads the
slices it needs from the single `state` dict, adds its own, and returns `state` — a uniform,
composable contract (see docs/build/RESTRUCTURE_PLAN.md).

Phase A: these WRAP the existing, tested `run_parse` functions (no behaviour change); later
phases absorb the underlying logic here and retire the flat wrappers.

state slices touched here:
  file            {name, path}                         (input)
  cell_grid       the Layer-1 grid                     (heavy; kept as a side artifact)
  format          detect_format result
  structure_map   final_map (columns + anchors + subsections)
  structure_map_ai the raw AI map (unknown files) or None
  sub_results     per-subsection arithmetic results
  anchor_rows     light {row, description, values} rows for the lock / gate
  anchor_lock     {status, method, anchors, candidates, passing}
  anchors         the user's confirmed R/E/NOI picks   (written by the gate view)
  reconcile       light re-verify result               (check_anchors)
  signals         full per-row signal vectors          (classify)
  classification  {classified, noi, feedback, low_confidence_rows}  (classify)
"""
from .run_parse import parse_to_anchors, classify_within_anchors
from .anchor_lock import reconcile_triple


def stage1(state):
    """STAGE 1 — Layer 1 → format detect → resolve columns → light anchor rows → R−E=NOI
    lock. reads: file. writes: cell_grid, format, structure_map, structure_map_ai,
    sub_results, anchor_rows, anchor_lock."""
    s1 = parse_to_anchors(state["file"]["path"])
    return {**state,
            "cell_grid":        s1["cell_grid"],
            "format":           s1["format_result"],
            "structure_map":    s1["final_map"],
            "structure_map_ai": s1["structure_map"],
            "sub_results":      s1["sub_results"],
            "anchor_rows":      s1["anchor_rows"],
            "anchor_lock":      s1["anchor_lock"],
            "step":             "locked"}


def check_anchors(state):
    """Light `R − |E| = NOI` re-verify of state['anchors'] against the Stage-1 anchor_rows.
    reads: anchor_rows, anchor_lock, anchors. writes: reconcile. (No cell_grid needed.)"""
    locked = (state.get("anchor_lock") or {}).get("anchors") or {}
    picks  = state.get("anchors") or {}
    exp    = picks.get("expense_end_row")
    split  = locked.get("expense_split_rows") if exp == locked.get("expense_end_row") else None
    eunit  = split or [exp]
    rc = reconcile_triple(state.get("anchor_rows", []),
                          picks.get("revenue_end_row"), eunit, picks.get("noi_row"))
    return {**state, "reconcile": rc}


def classify(state):
    """STAGE 2 — apply the confirmed anchors → full signal extraction → classify + fact
    override → sections → NOI verify → (AI diagnosis on fail) → confidence flags.
    reads: cell_grid, structure_map, anchors, run_feedback?, max_iters?.
    writes: structure_map (anchors applied), signals, classification."""
    final_map = dict(state["structure_map"])
    picks = state.get("anchors")
    if picks is not None:
        locked_exp   = final_map.get("expense_end_row")
        locked_split = final_map.get("expense_split_rows")
        final_map["revenue_end_row"] = picks.get("revenue_end_row")
        final_map["expense_end_row"] = picks.get("expense_end_row")
        final_map["noi_row"]         = picks.get("noi_row")
        # keep the auto-detected split only if the user kept the pre-filled expense row
        final_map["expense_split_rows"] = (
            locked_split if picks.get("expense_end_row") == locked_exp else None)

    s2 = classify_within_anchors(state["cell_grid"], final_map,
                                 run_feedback=state.get("run_feedback", True),
                                 max_iters=state.get("max_iters", 5))
    return {**state,
            "structure_map":  final_map,
            "signals":        s2["signal_rows"],
            "classification": {"classified":          s2["classified"],
                               "noi":                 s2["noi"],
                               "feedback":            s2["feedback"],
                               "low_confidence_rows": s2["low_confidence_rows"]},
            "step": "classified"}
