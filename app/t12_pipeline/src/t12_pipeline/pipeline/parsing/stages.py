"""The step catalog and the composite stages, all in run-state form (`run(state) -> state`).

Every pipeline module now exposes its own `run(state)` step (see each module). This file
composes them into the two coherent stages the app runs, and publishes `STEPS` — the registry
the bridge's `run_step` dispatches on and the views sequence.

  stage1   = extract_grid → detect_format → resolve_columns → extract_anchor_rows → lock_anchors
  classify = (apply confirmed anchors) → extract_signals → classify → sections → verify_noi
             → [NOI fail? → diagnose → apply_fix → re-verify (loop)] → flag_low_confidence
  reverify = apply the user's class edits → verify_noi → flag_low_confidence  (no AI, no
             re-classify — the review page's own re-entry into the NOI check)

Every fork here is owned by the FLOW (decided by the data / the arithmetic), never by a caller
flag — a caller can only re-enter a step, not switch part of it off.

See docs/build/RESTRUCTURE_PLAN.md.
"""
from t12_pipeline.config.rulebook_utils import get_rulebook_categories, load_latest_rulebook
from ..mapping.map_blocks import map_results, apply_row_edit
from ..mapping.find_mapping import run_ai_mapping
from . import cell_grid, format_detect, structure_map, extract, anchor_lock, sections, noi, feedback
from . import classify as classify_mod
from . import parse_log
from .legacy_adapter import column_headers, res_from_state, to_annotated


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


def reverify(state):
    """STAGE 2 re-entry — the user changed one or more rows' class on the review page.
    apply the edits → verify_noi → flag_low_confidence, re-entering the SAME noi node the
    first pass used, so the number on the page is always the pipeline's number.

    Deliberately does NOT re-classify (that would recompute the scores from the signals and
    silently overwrite the user's edit — what the NOI page's old Recompute did) and does NOT
    call the AI (it already had its turn in `classify`; re-running it here would just fight the
    user, one LLM call per edit). Sections aren't reassigned either: a section is positional
    (which side of the locked anchors the row sits on), so a class edit cannot move one.
    reads/writes: classification. inputs: class_edits={row: CLASS}."""
    cls = state["classification"]
    fm  = state["structure_map"]
    # only the NOI target itself is off-limits — the user may reclassify anything between the
    # anchors, including the arithmetic's subsection subtotals (the page offers no dropdown on
    # the anchors, but the workflow doesn't rely on the page for that).
    locked = {fm.get("revenue_end_row"), fm.get("expense_end_row"), fm.get("noi_row"),
              *(fm.get("expense_split_rows") or [])} - {None}
    edits = [{"row": int(r), "corrected_class": c}
             for r, c in (state.get("class_edits") or {}).items()]

    state = {**state, "classified": feedback.apply_corrections(cls["classified"], edits,
                                                               locked, source="manual")}
    state = noi.run(state)
    state = classify_mod.run_flag(state)
    parse_log.stage2_classify(state)
    parse_log.stage2_noi(state, "re-verify")

    classification = {**cls, "classified": state["classified"], "noi": state["noi"],
                      "low_confidence_rows": state["low_confidence_rows"]}
    keep = {k: v for k, v in state.items()
            if k not in ("classified", "noi", "low_confidence_rows", "class_edits")}
    return {**keep, "classification": classification, "step": "classified"}


def stage3_mapping(state):
    """STAGE 3 — map every classified DATA row to a canonical category: rulebook lookup, then
    the AI fallback for whatever it missed. The anchor flags ride in via to_annotated straight
    from the LOCKED anchors, so we map against the rows the user confirmed.
    reads: classification, structure_map, cell_grid, signals, file. writes: mapping, mapping_logs."""
    parse_log.stage3_start(state["file"]["name"])
    rulebook = load_latest_rulebook()
    annotated = to_annotated(res_from_state(state), state["file"]["name"])
    auto_mapped = map_results(annotated, rulebook)                  # 3a — rulebook
    mapped, run_logs = run_ai_mapping(auto_mapped, rulebook)        # 3b — AI fallback
    parse_log.stage3_end(mapped, state["file"]["name"])
    out = {**state, "mapping": mapped, "step": "mapped"}
    if run_logs:
        out["mapping_logs"] = run_logs
    return out


def stage3_update_mapping(state):
    """STAGE 3 re-entry — the user overrode one row's category / flip_sign on data_review.
    Applies the edit onto the EXISTING mapping. Deliberately does NOT re-map and does NOT call
    the AI: re-running the stage would discard the mapping being reviewed (the same mistake the
    NOI page's Recompute made with the classification). Nor does it re-verify NOI — unlike a
    Stage-2 class edit, a category is a label and flip_sign is an output sign convention;
    neither changes a sum the pipeline verified, and data_review shows Stage 2's NOI directly.
    reads/writes: mapping. inputs: row_edit={row, category?, flip_sign?, note?} — only the keys
    the user actually changed."""
    e = state.get("row_edit") or {}
    edit = {k: e[k] for k in ("category", "flip_sign", "note") if k in e}
    mapped = apply_row_edit(state["mapping"], e.get("row"),
                            valid_categories=get_rulebook_categories(load_latest_rulebook()),
                            **edit)
    return {**state, "mapping": mapped}


def stage3_bulk_update_mapping(state):
    """STAGE 3 re-entry — the user set ONE category on many selected rows at once (data_review
    bulk action). Applies the SAME override to every listed row; like stage3_update_mapping it
    only overrides `final_mapping` (no re-map, no AI, no NOI re-verify). `category` may be None to
    clear the override on all selected rows. inputs: bulk={rows:[int], category:str|None}."""
    b = state.get("bulk") or {}
    category = b.get("category") or None
    valid = get_rulebook_categories(load_latest_rulebook())
    mapped = state["mapping"]
    for row in b.get("rows", []):
        mapped = apply_row_edit(mapped, row, category=category, valid_categories=valid)
    return {**state, "mapping": mapped}


# ── The workflow registry — the ONLY things a view may run ────────────────────
# Each entry is a complete, valid transition, named <stage>_<user action>. Individual module
# steps are deliberately NOT exposed: handing a caller raw nodes invites it to assemble its own
# pipeline (skip a node, reorder, re-enter mid-stage), which is how the NOI page silently wiped
# the AI's corrections. A new need = a new workflow here, never a new handle.
# Tests don't use this registry — they import the modules directly and mock the AI agents.
STEPS = {
    "stage1_parse":          stage1,                # upload        → parse up to the anchor lock
    "stage1_check_anchors":  check_anchors,         # gate          → re-verify picks (read-only)
    "stage2_classify":       classify,              # gate confirm  → Stage 2 (AI on NOI fail)
    "stage2_reverify":       reverify,              # Stage-2 edit  → re-verify NOI (no AI)
    "stage3_mapping":        stage3_mapping,        # review submit → rulebook + AI fallback
    "stage3_update_mapping": stage3_update_mapping, # Stage-3 edit  → apply a mapping override
    "stage3_bulk_update_mapping": stage3_bulk_update_mapping,  # Stage-3 bulk → one category, many rows
}
