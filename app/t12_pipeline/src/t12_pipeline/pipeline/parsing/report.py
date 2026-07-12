"""Console report — render a `parse_file()` result the way the notebook orchestrator
did (format table, signal rows, arithmetic evidence, anchor candidates, score
breakdown, NOI table, diagnosis). Pure rendering over the returned dict — no pipeline
logic. For debugging / understanding what happened on a file.

    python -m t12_pipeline.pipeline.parsing.report "<file.xlsx>" [--explain-all]
"""
from collections import Counter

from .classify import CLASSES, CLASS_SIGNALS, SIGNAL_FUNCS, reconcile_leaf_data
from .format_detect import KINDS, NCOLS, COL_LETTERS

_SHORT = ["META", "SECHDR", "SUBHDR", "DATA", "SUBTOT", "SECTOT", "METRIC"]

# most-important-first column order for the signal table
_SIGNAL_COL_ORDER = [
    "arithmetic_sum_of_above", "has_values", "is_bold", "total_keyword",
    "is_metric", "top_border", "has_formula", "all_caps", "in_metadata_band",
    "column_depth", "whitespace_depth", "is_subsection_subtotal",
    "is_subsection_header", "value_count", "position_in_file",
]


def _hr(title):
    print("\n" + "=" * 78 + f"\n### {title}\n" + "=" * 78)


# ── the notebook print helpers, re-pointed at the result rows ─────────────────
def print_signal_rows(rows, limit=None):
    if not rows:
        print("(no rows)"); return
    present = [k for k in rows[0] if not k.startswith("_") and k not in ("row", "description")
               and not isinstance(rows[0][k], (list, dict))]
    keys = [k for k in _SIGNAL_COL_ORDER if k in present] + \
           [k for k in present if k not in _SIGNAL_COL_ORDER]
    header = f"{'row':>4}  {'description':<30}  " + "  ".join(keys)
    print(header); print("-" * len(header))
    for r in (rows if limit is None else rows[:limit]):
        cells = []
        for k in keys:
            v = r[k]
            if isinstance(v, bool):
                v = "Y" if v else "."
            cells.append(f"{str(v):>{len(k)}}")
        print(f"{r['row']:>4}  {r['description'][:30]:<30}  " + "  ".join(cells))


def print_arithmetic_evidence(rows, only_fired=True, limit=None):
    shown = [r for r in rows if r.get("arithmetic", {}).get("member_rows")
             and (r["arithmetic"]["fired"] or not only_fired)]
    if not shown:
        print("  (no rows matched an arithmetic sum-of-above)"); return
    for r in (shown if limit is None else shown[:limit]):
        a = r["arithmetic"]; mr = a["member_rows"]
        rng = f"{mr[0]}..{mr[-1]}" if len(mr) > 1 else f"{mr[0]}"
        mark = "✓" if a["fired"] else "✗"
        print(f"  row {r['row']:>3} {r['description'][:24]:<24} = Σ rows {rng:<10} ({len(mr):>2}) "
              f"= {a['sum']:>15,.2f} vs target {a['target']:>15,.2f}  diff {a['diff']:>10,.2f} / tol {a['tolerance']:>8,.2f}  {mark}")
        if len(a["member_values"]) <= 8:
            print(f"        values: {' + '.join(f'{x:,.2f}' for x in a['member_values'])}")


def _sig_label(s, r):
    ev = r.get("signal_evidence", {})
    if s in ("subtotal_marked", "not_subtotal_marked"):
        by = ev.get("subtotal_marked_by") or []
        return f"{s}({'+'.join(by) or 'none'})"
    if s == "total_keyword" and ev.get("total_keyword_hit"):
        return f"total_keyword('{ev['total_keyword_hit']}')"
    if s == "is_metric" and ev.get("metric_keyword_hit"):
        return f"is_metric('{ev['metric_keyword_hit']}')"
    return s


def explain_scores(rows, example_rows=None, top_k=2, which="examples"):
    by_row = {r["row"]: r for r in rows}
    if example_rows is None:
        if which == "all":
            example_rows = [r["row"] for r in rows]
        else:
            seen = {}
            for r in rows:
                seen.setdefault(r["class"], r["row"])
            example_rows = list(seen.values())
    for rn in example_rows:
        r = by_row.get(rn)
        if r is None:
            continue
        sc = r["scores"]
        ranked = sorted(CLASSES, key=lambda c: sc[c], reverse=True)
        conf = r.get("confidence")
        conf_s = f"  conf {conf:.0%}" if conf is not None else ""
        print(f"\nrow {r['row']}  {r['description'][:44]!r}  →  {r['class']}  ({sc[r['class']]:.0%}){conf_s}")
        for c in ranked[:top_k]:
            sigs = CLASS_SIGNALS[c]
            hit  = [_sig_label(s, r) for s in sigs if SIGNAL_FUNCS[s](r)]
            miss = [_sig_label(s, r) for s in sigs if not SIGNAL_FUNCS[s](r)]
            tag = "WINNER " if c == ranked[0] else "runner "
            print(f"    {tag}{c:<20} {len(hit)}/{len(sigs)} = {sc[c]:.0%}   "
                  f"hit[{', '.join(hit) or '—'}]  miss[{', '.join(miss) or '—'}]")


def print_classified_rows(rows, limit=None):
    hdr = f"{'row':>4}  {'description':<28}  {'CLASS':<20} " + " ".join(f"{s:>6}" for s in _SHORT) + "   conf"
    print(hdr); print("-" * len(hdr))
    for r in (rows if limit is None else rows[:limit]):
        sc = r["scores"]
        conf = r.get("confidence")
        print(f"{r['row']:>4}  {r['description'][:28]:<28}  {r['class']:<20} "
              + " ".join(f"{sc[c]:>6.2f}" for c in CLASSES)
              + (f"   {conf:.2f}" if conf is not None else ""))


# ── the full report ──────────────────────────────────────────────────────────
def _fmt_noi_cell(t):
    a, c, ok = t
    mark = "  " if ok is None else ("ok" if ok else "XX")
    av = "   --   " if a is None else f"{a:,.0f}"
    cv = "   --   " if c is None else f"{c:,.0f}"
    return f"{av} / {cv} {mark}"


def print_stage1_report(res, *, show_all_rows=True):
    """Stage 1 — format detection, column resolution, signal extraction, anchor lock."""
    fm = res["final_map"]; fr = res["format_result"]
    print(f"format : {res['format']}  (confidence {fr['confidence']}, {fr['reason']})")

    _hr("Module 4 — Format detection")
    C, F = fr["counts"], fr["fractions"]
    print(f"  rows_with_text = {fr['rows_with_text']}")
    print(f"    {'kind':<15} " + "  ".join(f"{c.upper():>11}" for c in COL_LETTERS))
    for k in KINDS:
        print(f"    {k:<15} " + "  ".join(f"{f'{C[k][c]}={F[k][c]}':>11}" for c in range(NCOLS)))
    print("  scores : " + "   ".join(f"{k}={v}" for k, v in fr["scores"].items()))

    _hr("Column resolution / structure map")
    vc = fm["value_columns"]
    print(f"  value cols {vc[0]}..{vc[-1]} ({len(vc)}) | desc cols {', '.join(fm['description_columns'])} | "
          f"month_header {fm.get('month_header_row')} | data_start {fm.get('data_start_row')}")
    if res.get("sub_results"):
        print(f"\n  subsection hierarchy — {len(res['sub_results'])} sub-groups, "
              f"{len(fm.get('validated_subsection_subtotal_rows', []))} arithmetically validated:")
        for r in res["sub_results"]:
            mark = "ok" if r["ok"] else "XX"
            mr = r["member_rows"]; rng = f"{mr[0]}..{mr[-1]}" if len(mr) > 1 else (str(mr[0]) if mr else "-")
            tgt = "None" if r["target"] is None else f"{r['target']:,.2f}"
            print(f"    {mark} row {r['row']:>3} {r['name'][:24]:<24} = Σ {r['members']:>2} leaves (rows {rng:<10}) = {r['sum']:>15,.2f}  vs {tgt}")

    _hr("Module 9 — Signal extraction")
    print_signal_rows(res["signal_rows"], limit=None if show_all_rows else 40)
    print("\n  arithmetic sum-of-above evidence (rows whose value matched a running sum above):")
    print_arithmetic_evidence(res["signal_rows"], only_fired=True)

    _hr("Module 9b — Stage 1 anchor lock (R − E = NOI decides)")
    al = res["anchor_lock"]
    print(f"  candidates : {al['candidates']}")
    print(f"  passing triples ({len(al['passing'])}):")
    for (rr, eu, nr) in al["passing"]:
        print(f"    R{rr} − E{eu} = N{nr}")
    a = al["anchors"]
    tag = "" if al["status"] == "AUTO" else "   ⚠ would go to the manual gate"
    print(f"  → status {al['status']} ({al['method']}) — locked "
          f"R={a and a['revenue_end_row']} E={a and a['expense_end_row']} N={a and a['noi_row']}{tag}")


def print_stage2_report(res, *, explain_all=False, show_all_rows=True):
    """Stage 2 — classification + fact override, section assignment, NOI, diagnosis loop."""
    fm = res["final_map"]
    _hr("Module 10 — Classification (7-class) + fact override")
    dist = Counter(r["class"] for r in res["classified"])
    print("  class distribution: " + "  ".join(f"{c}={dist.get(c, 0)}" for c in CLASSES))
    print()
    print_classified_rows(res["classified"], limit=None if show_all_rows else 40)
    print("\n  SCORE BREAKDOWN — " + ("every row" if explain_all else "one example row per class") + " (winner vs runner-up):")
    explain_scores(res["classified"], which=("all" if explain_all else "examples"))
    rec = reconcile_leaf_data(res["classified"], res["cell_grid"], fm)
    print("\n  leaf-DATA reconciliation (sum of DATA rows vs the vendor grand total):")
    for side in ("revenue", "expense", "noi"):
        d = rec[side]; n = f"  [{d['n']} DATA rows]" if "n" in d else ""
        print(f"    {side:<7}: {d['computed']:>15,.2f} vs {d['vendor']:>15,.2f}  {'PASS' if d['ok'] else 'FAIL'}{n}")

    _hr("Module 11 — Section assignment (from the locked anchors)")
    sec = Counter(r.get("section") for r in res["classified"])
    print("  " + "  ".join(f"{s}={sec.get(s, 0)}" for s in ("metadata", "revenue", "expense", "capex")))

    _hr("Module 12 — NOI verification (per month AND total)")
    noi = res["noi"]
    hdr = f"  {'col':<5} {'revenue  act / comp':<26} {'expense  act / comp':<26} {'NOI  act / comp':<26}"
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    for m in noi["months"]:
        print(f"  {m['col']:<5} {_fmt_noi_cell(m['rev']):<26} {_fmt_noi_cell(m['exp']):<26} {_fmt_noi_cell(m['noi']):<26}")
    print(f"\n  OVERALL NOI VERIFICATION: {'PASS' if noi['overall_pass'] else 'FAIL'}")

    if res.get("feedback"):
        _hr("Modules 13-14 — Diagnosis + Feedback loop")
        fb = res["feedback"]
        print(f"  loop status: {fb['status']}  after {fb['iterations']} iteration(s)")
        for h in fb["history"]:
            after = h.get("noi_fail_cols_after")
            delta = f"  NOI-fail cols {h['noi_fail_cols_before']} → {after}" if after is not None else ""
            print(f"    iter {h['iter']}: verdict={h['verdict']}  proposed_fixes={h['proposed_fixes']}{delta}")
            for fx in h.get("fixes", []):
                print(f"        row {fx['row']}: {fx['from']} → {fx['to']}")
                if fx.get("reason"):
                    print(f"           reason: {fx['reason']}")
        dg = fb["diagnosis"]
        if getattr(dg, "data_inconsistency", None):
            print(f"  data inconsistency: {dg.data_inconsistency}")
        if getattr(dg, "user_message", None):
            print(f"  user message: {dg.user_message}")


def print_parse_report(res, *, explain_all=False, show_all_rows=True):
    """Full one-pass report (CLI / testing): Stage 1 then Stage 2."""
    print_stage1_report(res, show_all_rows=show_all_rows)
    print_stage2_report(res, explain_all=explain_all, show_all_rows=show_all_rows)


def main(argv=None):
    import sys
    from .run_parse import parse_file
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print('usage: python -m t12_pipeline.pipeline.parsing.report "<file.xlsx>" [--explain-all]')
        return
    explain_all = "--explain-all" in args
    paths = [a for a in args if not a.startswith("--")]
    for p in paths:
        print("#" * 78 + f"\n# {p}\n" + "#" * 78)
        print_parse_report(parse_file(p), explain_all=explain_all)


if __name__ == "__main__":
    main()
