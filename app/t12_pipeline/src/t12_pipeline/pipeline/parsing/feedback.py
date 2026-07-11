"""Module 14 — Feedback loop (diagnose → apply fix → re-verify, arithmetic-gated).

When NOI fails, iterate: the diagnosis agent names the mislabeled rows, we apply its
corrected classes, re-run the NOI check, and repeat. A fix is accepted ONLY if the
money now reconciles — the AI proposes, the arithmetic decides. Locked anchor rows
are never reclassified, so the loop can't move the NOI target.

Ported verbatim from notebook Module 14.
"""
from .diagnosis import run_diagnosis_agent
from .noi import verify_noi
from .classify import CLASSES


def apply_corrections(classified, problem_rows, locked=frozenset()):
    """Return a copy of `classified` with the diagnosis's corrected_class applied to
    the named rows (only rows/classes that are valid). Locked anchor rows are NEVER
    reclassified — the Stage-1 arithmetic already fixed them, so diagnosis can only
    move the rows between the anchors, never the NOI target itself."""
    fix = {pr["row"]: pr["corrected_class"] for pr in problem_rows
           if pr.get("row") is not None and pr.get("corrected_class") in CLASSES
           and pr["row"] not in locked}
    out = []
    for r in classified:
        r2 = dict(r)
        if r["row"] in fix:
            r2["class"] = fix[r["row"]]
        out.append(r2)
    return out


def run_feedback_loop(classified, grid, final_map, noi_res, max_iters=3):
    """Diagnose → apply → re-verify, up to max_iters. Accept a fix only when NOI
    reconciles. Returns dict(status, classified, noi, iterations, history, diagnosis).
    status ∈ {FIXED, DATA_PROBLEM, UNCERTAIN, UNRESOLVED}."""
    def _fails(noi):   # how many month columns still don't reconcile
        return sum(1 for m in noi["months"] if m["noi"][2] is False)
    locked = ({final_map.get("revenue_end_row"), final_map.get("expense_end_row"),
               final_map.get("noi_row")} | set(final_map.get("validated_subsection_subtotal_rows", []))) - {None}
    cur, cur_noi, history, diag = classified, noi_res, [], None
    for it in range(1, max_iters + 1):
        diag = run_diagnosis_agent(cur, grid, final_map, cur_noi)
        fixes = diag.problem_rows or []
        entry = {"iter": it, "verdict": diag.verdict, "proposed_fixes": len(fixes),
                 "noi_fail_cols_before": _fails(cur_noi),
                 "fixes": [{"row": pr.row, "from": pr.current_class, "to": pr.corrected_class,
                            "reason": pr.reason} for pr in fixes]}
        if diag.verdict == "DATA_PROBLEM":
            history.append(entry)
            return {"status": "DATA_PROBLEM", "classified": cur, "noi": cur_noi,
                    "iterations": it, "history": history, "diagnosis": diag}
        if diag.verdict != "CLASSIFICATION_PROBLEM" or not fixes:
            history.append(entry)
            return {"status": diag.verdict or "UNCERTAIN", "classified": cur, "noi": cur_noi,
                    "iterations": it, "history": history, "diagnosis": diag}
        cur = apply_corrections(cur, [pr.model_dump() for pr in fixes], locked)
        cur_noi = verify_noi(cur, grid, final_map)
        entry["noi_fail_cols_after"] = _fails(cur_noi)
        history.append(entry)
        if cur_noi["overall_pass"]:
            return {"status": "FIXED", "classified": cur, "noi": cur_noi,
                    "iterations": it, "history": history, "diagnosis": diag}
    return {"status": "UNRESOLVED", "classified": cur, "noi": cur_noi,
            "iterations": max_iters, "history": history, "diagnosis": diag}
