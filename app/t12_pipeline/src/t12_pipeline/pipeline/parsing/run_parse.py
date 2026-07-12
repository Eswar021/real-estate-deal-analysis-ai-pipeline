"""Anchor-first parse runner — two stages the app runs separately.

  Stage 1  `parse_to_anchors`      — format detect → resolve columns (template/AI) →
                                      LIGHT row build ({row, description, values}) →
                                      anchor lock (R−E=NOI). NO signal extraction yet;
                                      stops here so the anchor gate can confirm the 3 rows.
  Stage 2  `classify_within_anchors`— dynamic feature extraction (the full signal vector)
                                      → classify + fact override → section from the
                                      (confirmed) anchors → NOI verify → diagnosis loop.

`parse_file` runs both in one pass (for the CLI report / testing). In the app the
bridge runs Stage 1 at upload and Stage 2 only after the anchors are confirmed.
"""
from .cell_grid import extract_cell_grid
from .format_detect import detect_format
from .structure_map import build_known_map, build_final_map
from .structure_agent import run_structure_agent
from .extract import extract_anchor_rows, extract_row_signals_dynamic
from .anchor_lock import lock_anchors, apply_anchor_overrides
from .classify import classify_rows, flag_low_confidence
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


def _lock_payload(lock):
    return {"status": lock["status"], "method": lock["method"], "anchors": lock["anchors"],
            "candidates": lock["candidates"], "passing": lock["passing"]}


def parse_to_anchors(xlsx_path):
    """STAGE 1 — up to and including the anchor lock. NO signal extraction, NO
    classification. Builds only the light {row, description, values} rows the lock needs.
    Returns the Stage-1 state (cell_grid, final_map with the locked anchors written in,
    anchor_rows, anchor_lock, sub_results, format)."""
    cell_grid  = extract_cell_grid(xlsx_path)
    fmt_result = detect_format(cell_grid)
    fmt        = fmt_result["format"]

    final_map, sub_results, structure_map = resolve_structure_map(fmt, cell_grid)
    anchor_rows = extract_anchor_rows(cell_grid, final_map)     # light: {row, description, values}
    lock = lock_anchors(anchor_rows, final_map)
    if lock["anchors"]:
        a = lock["anchors"]
        final_map["revenue_end_row"]    = a["revenue_end_row"]
        final_map["expense_end_row"]    = a["expense_end_row"]
        final_map["noi_row"]            = a["noi_row"]
        # a vendor that splits expenses across >1 grand-total row (controllable +
        # non-controllable) has no single expense total — carry both legs so NOI
        # verification sums them instead of reading only the bottom-most row.
        final_map["expense_split_rows"] = a.get("expense_split_rows")

    return {
        "format": fmt,
        "format_result": fmt_result,
        "final_map": final_map,
        "sub_results": sub_results,
        "structure_map": structure_map.model_dump() if structure_map else None,
        "anchor_lock": _lock_payload(lock),
        "cell_grid": cell_grid,
        "anchor_rows": anchor_rows,
    }


def _derive_subsection_subtotals(signal_rows, final_map):
    """Known files arrive with no AI subsection map. The arithmetic scan already fires on
    every row whose value = the running sum of the data rows above it — those ARE the
    subsection subtotals. Return them, minus the grand anchors (handled separately)."""
    anchors = {final_map.get("revenue_end_row"), final_map.get("expense_end_row"),
               final_map.get("noi_row"), *(final_map.get("expense_split_rows") or [])}
    anchors.discard(None)
    return sorted(r["row"] for r in signal_rows
                  if r.get("arithmetic_sum_of_above") and r["row"] not in anchors)


def classify_within_anchors(cell_grid, final_map, *, run_feedback=True, max_iters=5):
    """STAGE 2 — dynamic feature extraction (the full signal vector) → classify + fact
    override → sections → NOI → diagnosis. Runs only after the anchors are confirmed, so
    `final_map` already carries the locked revenue/expense/noi rows. This is where the
    heavy per-row signal extraction happens — never at upload.
    Returns {classified, noi, feedback, signal_rows, low_confidence_rows}."""
    signal_rows = extract_row_signals_dynamic(cell_grid, final_map)

    # enh. (b): a known file has no AI subsection map — derive it arithmetically so the
    # fact-override marks subsection subtotals the same way it does for AI-mapped files.
    if not final_map.get("validated_subsection_subtotal_rows"):
        final_map = {**final_map,
                     "validated_subsection_subtotal_rows": _derive_subsection_subtotals(signal_rows, final_map)}

    classified = apply_anchor_overrides(classify_rows(signal_rows, final_map), final_map)
    assign_sections(classified, final_map)
    noi = verify_noi(classified, cell_grid, final_map)

    feedback = None
    if not noi["overall_pass"] and run_feedback and final_map.get("noi_row"):
        feedback = run_feedback_loop(classified, cell_grid, final_map, noi, max_iters=max_iters)
        classified, noi = feedback["classified"], feedback["noi"]

    low_confidence_rows = flag_low_confidence(classified)
    return {"classified": classified, "noi": noi, "feedback": feedback,
            "signal_rows": signal_rows, "low_confidence_rows": low_confidence_rows}


def parse_file(xlsx_path, *, run_feedback=True, max_iters=5):
    """Convenience combo (CLI report / testing): Stage 1 + Stage 2 in one pass."""
    s1 = parse_to_anchors(xlsx_path)
    s2 = classify_within_anchors(s1["cell_grid"], s1["final_map"],
                                 run_feedback=run_feedback, max_iters=max_iters)
    return {**s1, **s2}
