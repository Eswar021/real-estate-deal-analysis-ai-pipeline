"""Anchor-first parse runner — wires the parsing modules into one pass.

Flow (shared for known + unknown): format detect → resolve columns (template map for
known, AI structure agent for unknown) → dynamic extract → Stage-1 anchor lock
(R−E=NOI) → classify + fact override → section from anchors → NOI verify →
diagnosis + feedback loop on NOI fail.

`parse_file(xlsx)` returns a single result dict; the bridge/manifest layer wires this
to per-upload stage files.
"""
from .cell_grid import extract_cell_grid
from .format_detect import detect_format
from .structure_map import build_known_map, build_final_map
from .structure_agent import run_structure_agent
from .extract import extract_row_signals_dynamic
from .anchor_lock import lock_anchors, apply_anchor_overrides
from .classify import classify_rows
from .sections import assign_sections
from .noi import verify_noi
from .feedback import run_feedback_loop

KNOWN_FORMATS = ("code_in_a_desc_in_b", "embedded_code_in_a", "no_code")


def resolve_structure_map(fmt, cell_grid):
    """Template map for a known format (no AI); AI structure map for unknown.
    Returns (final_map, sub_results, structure_map_or_None)."""
    if fmt in KNOWN_FORMATS:
        return build_known_map(fmt, cell_grid), [], None
    structure_map = run_structure_agent(cell_grid)
    final_map, sub_results = build_final_map(structure_map.model_dump(), cell_grid)
    return final_map, sub_results, structure_map


def parse_file(xlsx_path, *, run_feedback=True, max_iters=5):
    """Full anchor-first parse of one T12 workbook. Returns a dict with the format,
    final_map (with locked anchors), the anchor-lock result, the classified rows
    (class + section + confidence), the NOI verification, and (on NOI fail) the
    feedback-loop result."""
    cell_grid  = extract_cell_grid(xlsx_path)
    fmt_result = detect_format(cell_grid)
    fmt        = fmt_result["format"]

    final_map, sub_results, structure_map = resolve_structure_map(fmt, cell_grid)

    # ── extract → Stage-1 anchor lock ──
    signal_rows = extract_row_signals_dynamic(cell_grid, final_map)
    lock = lock_anchors(signal_rows, final_map)
    if lock["anchors"]:
        a = lock["anchors"]
        final_map["revenue_end_row"] = a["revenue_end_row"]
        final_map["expense_end_row"] = a["expense_end_row"]
        final_map["noi_row"]         = a["noi_row"]

    # ── classify + fact override → sections → NOI ──
    classified = apply_anchor_overrides(classify_rows(signal_rows, final_map), final_map)
    assign_sections(classified, final_map)
    noi = verify_noi(classified, cell_grid, final_map)

    # ── diagnosis + feedback loop only on NOI fail (needs a locked NOI row) ──
    feedback = None
    if not noi["overall_pass"] and run_feedback and final_map.get("noi_row"):
        feedback = run_feedback_loop(classified, cell_grid, final_map, noi, max_iters=max_iters)
        classified, noi = feedback["classified"], feedback["noi"]

    return {
        "format": fmt,
        "format_result": fmt_result,
        "final_map": final_map,
        "sub_results": sub_results,
        "structure_map": structure_map.model_dump() if structure_map else None,
        "anchor_lock": {"status": lock["status"], "method": lock["method"],
                        "anchors": lock["anchors"], "candidates": lock["candidates"],
                        "passing": lock["passing"]},
        "cell_grid": cell_grid,
        "signal_rows": signal_rows,
        "classified": classified,
        "noi": noi,
        "feedback": feedback,
    }
