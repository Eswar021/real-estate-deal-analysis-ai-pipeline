"""Structured, profile-aware logging for the parse pipeline — all the rendering in ONE place.

The pipeline steps call these one-liners (`parse_log.stage1(state)`, `parse_log.stage2_*`,
`parse_log.diagnosis_*`, `parse_log.stage3`) so the step code stays clean. Each stage emits a
banner → step lines → end banner. What gets logged depends on the active profile
(`config.log_config`): 'summary' = banners + summaries + the anchor/classification/NOI tables;
'verbose' also dumps per-row scoring + full diagnosis reasons (LLM input/output is logged
separately by `llm_client`). File-only — the terminal stays clean.
"""
import logging
from collections import Counter

from t12_pipeline.config.log_config import is_verbose

_S1 = logging.getLogger("t12.stage1")
_S2 = logging.getLogger("t12.stage2")
_S3 = logging.getLogger("t12.stage3")


def _fmt(v):
    return f"{v:,.0f}" if isinstance(v, (int, float)) else ("" if v is None else str(v))


def _last(values):
    vals = [x for x in (values or []) if x is not None]
    return vals[-1] if vals else None


def _banner(title):
    return "═" * 8 + f" {title} " + "═" * 8


def _anchor_table(rows):
    out = [f"{'row':>4}  {'description':<44}  {'total':>14}"]
    for r in rows:
        out.append(f"{r['row']:>4}  {r.get('description', '')[:44]:<44}  {_fmt(_last(r.get('values'))):>14}")
    return "\n".join(out)


def _classified_table(rows):
    """One table = the classification AND its evidence: `margin` and `signals` (WHICH raw
    signals fired) say why the row landed in that class. Shown in every profile; without it a
    class is an unexplained assertion.

    `margin` is NOT a confidence percentage — it is the winning class's score minus the
    runner-up's. 0.20 is what a PERFECT classification looks like here (the winner scores 1.00,
    the runner-up 0.80, because the classes share signals). Use the `verbose` profile's
    per-row scoring table to see the actual per-class scores.
    """
    out = [f"{'row':>4}  {'description':<34}  {'class':<20} {'section':<8} {'total':>13} "
           f"{'margin':>6} {'src':<6} signals"]
    for r in rows:
        out.append(f"{r['row']:>4}  {r.get('description', '')[:34]:<34}  {r['class']:<20} "
                   f"{(r.get('section') or ''):<8} {_fmt(_last(r.get('values'))):>13} "
                   f"{(r.get('confidence') or 0):>6.2f} {(r.get('source') or 'auto'):<6}"
                   f" {','.join(r.get('_signals', []))}")
    return "\n".join(out)


# short column heads for the 7 classes, in CLASSES order
_ABBR = {"METADATA": "META", "SECTION_HEADER": "SECH", "SUBSECTION_HEADER": "SUBH",
         "DATA": "DATA", "SUBSECTION_SUBTOTAL": "SUBT", "SECTION_SUBTOTAL": "SECT",
         "COMPUTED_METRIC": "METR"}


def _scoring_table(rows):
    """Verbose: WHY each row got its class — its score against ALL SEVEN classes.

    Read a cell as: the fraction of THAT class's own signals this row satisfies (see
    classify.CLASS_SIGNALS). `[x.xx]` marks the class the row was ASSIGNED. So a `[1.00]`
    means the row matched every signal its class asks for.

    Where the bracket is NOT on the highest number, the assignment did not come from the
    classifier — the arithmetic fact-override, the AI diagnosis, or the user changed it. The
    `src` column says which, so a disagreement between score and class is readable at a glance.
    """
    head = " ".join(f"{a:^6}" for a in _ABBR.values())
    out = [f"{'row':>4}  {'description':<30}  {head}  {'class':<20} {'margin':>6} {'src':<6} signals",
           "      each cell = fraction of THAT class's signals satisfied · [x] = the class assigned",
           "      [x] NOT on the highest = the score didn't decide it: the arithmetic fact-override"
           " (locked anchor / validated subtotal, src=auto), the AI diagnosis (src=ai), or the user"
           " (src=manual)"]
    for r in rows:
        sc = r.get("scores") or {}
        cells = " ".join(
            (f"[{sc[c]:4.2f}]" if c == r.get("class") else f" {sc[c]:4.2f} ") if c in sc else f"{'-':^6}"
            for c in _ABBR)
        out.append(f"{r['row']:>4}  {(r.get('description') or '')[:30]:<30}  {cells}  "
                   f"{r.get('class', ''):<20} {(r.get('confidence') or 0):>6.2f} "
                   f"{(r.get('source') or 'auto'):<6} {','.join(r.get('_signals', []))}")
    return "\n".join(out)


def _noi_table(noi):
    out = [f"{'col':<4} {'rev(comp)':>13} {'rev(vend)':>13} {'exp(comp)':>13} "
           f"{'exp(vend)':>13} {'noi(comp)':>13} {'noi(vend)':>13}  ok"]
    for m in noi.get("months", []):
        out.append(f"{m['col']:<4} {_fmt(m['rev'][1]):>13} {_fmt(m['rev'][0]):>13} "
                   f"{_fmt(m['exp'][1]):>13} {_fmt(m['exp'][0]):>13} "
                   f"{_fmt(m['noi'][1]):>13} {_fmt(m['noi'][0]):>13}  {'ok' if m['noi'][2] else 'XX'}")
    return "\n".join(out)


# ── Stage 1 ───────────────────────────────────────────────────────────────────
def stage1(state):
    file = (state.get("file") or {}).get("name")
    fmt = state.get("format") or {}
    sm = state.get("structure_map") or {}
    vc = sm.get("value_columns") or ["?"]
    lock = state.get("anchor_lock") or {}
    a = lock.get("anchors") or {}
    _S1.info("%s", _banner(f"STAGE 1 · anchor lock · {file}"))
    _S1.info("[stage1] format=%s (conf %.3f) · source=%s · value_cols=%s-%s · desc=%s · data_start=%s",
             fmt.get("format"), fmt.get("confidence") or 0, state.get("structure_source"),
             vc[0], vc[-1], ",".join(sm.get("description_columns") or []), sm.get("data_start_row"))
    _S1.info("[stage1] anchor lock: %s · R=%s E=%s N=%s split=%s", lock.get("status"),
             a.get("revenue_end_row"), a.get("expense_end_row"), a.get("noi_row"), a.get("expense_split_rows"))
    _S1.debug("[stage1] candidates=%s · passing=%s", lock.get("candidates"), lock.get("passing"))
    if is_verbose():
        _S1.debug("[stage1] anchor rows:\n%s", _anchor_table(state.get("anchor_rows", [])))
    _S1.info("%s", _banner(f"end STAGE 1 · lock={lock.get('status')}"))


# ── Stage 2 ───────────────────────────────────────────────────────────────────
def stage2_start(state):
    file = (state.get("file") or {}).get("name")
    sm = state.get("structure_map") or {}
    vc = sm.get("value_columns") or ["?"]
    _S2.info("%s", _banner(f"STAGE 2 · classify · {file}"))
    _S2.info("[stage2] signals extracted: %d rows · value_cols %s-%s",
             len(state.get("signals") or []), vc[0], vc[-1])


def _attach_signals(classified, signals):
    """For the verbose scoring table — which raw signals fired on each row."""
    sig = {s["row"]: s for s in (signals or [])}
    flags = [("bold", "is_bold"), ("total_kw", "total_keyword"), ("metric", "is_metric"),
             ("arith", "arithmetic_sum_of_above"), ("formula", "has_formula"), ("border", "top_border")]
    for r in classified:
        s = sig.get(r["row"], {})
        r["_signals"] = [name for name, key in flags if s.get(key)]


def stage2_classify(state):
    rows = state.get("classified") or (state.get("classification") or {}).get("classified", [])
    dist = Counter(r["class"] for r in rows)
    _S2.info("[stage2] classify + score: %d rows · %s", len(rows),
             " ".join(f"{k}={v}" for k, v in dist.items()))
    _attach_signals(rows, state.get("signals"))
    if is_verbose():
        _S2.debug("[stage2] per-row scoring (all 7 classes):\n%s", _scoring_table(rows))
    _S2.debug("[stage2] classification:\n%s", _classified_table(rows))


def stage2_noi(state, phase):
    noi = (state.get("classification") or {}).get("noi") or state.get("noi") or {}
    fails = sum(1 for m in noi.get("months", []) if m["noi"][2] is False)
    verdict = "PASS" if noi.get("overall_pass") else f"FAIL ({fails} months off)"
    _S2.info("[stage2] NOI verify (%s): %s", phase, verdict)
    _S2.debug("[stage2] NOI (%s):\n%s", phase, _noi_table(noi))


def stage2_end(state):
    noi = (state.get("classification") or {}).get("noi") or state.get("noi") or {}
    _S2.info("%s", _banner(f"end STAGE 2 · NOI={'PASS' if noi.get('overall_pass') else 'FAIL'}"))


# ── Stage 2 · diagnosis loop (called from feedback.py) ────────────────────────
def diagnosis_start(fail_cols):
    _S2.info("[stage2] diagnosis loop (NOI failed · %d cols):", fail_cols)


def diagnosis_iter(it, max_iters, diag, before, after=None):
    fixes = diag.problem_rows or []
    _S2.info("  ── iter %d/%d · %s · %d proposed fixes · fail_cols %d%s ──",
             it, max_iters, diag.verdict, len(fixes), before,
             f" → {after}" if after is not None else "")
    if is_verbose():
        if diag.user_message:
            _S2.debug("     agent message: %s", diag.user_message)
        if diag.reasoning:
            _S2.debug("     agent reasoning: %s", diag.reasoning)
    for pr in fixes:
        reason = pr.reason or ""
        _S2.debug("     row %s: %s → %s  (%s)", pr.row, pr.current_class, pr.corrected_class,
                  reason if is_verbose() else reason[:70])


def diagnosis_end(status, iters):
    _S2.info("  → diagnosis %s after %d iteration(s)", status, iters)


# ── Stage 3 · mapping ─────────────────────────────────────────────────────────
def stage3_start(file=None):
    _S3.info("%s", _banner(f"STAGE 3 · mapping{(' · ' + file) if file else ''}"))


def stage3_end(mapped, file=None):
    s = mapped.get("summary") or {}
    _S3.info("[stage3] %s data rows · %s mapped · %s unmapped",
             s.get("data_rows"), s.get("mapped"), s.get("unmapped"))
    if is_verbose():
        for r in mapped.get("rows", []):
            if r.get("type") == "data":
                _S3.debug("     row %s: %s → %s%s", r.get("row"), (r.get("description") or "")[:34],
                          r.get("mapping"), " [AI]" if r.get("mapping_source") == "ai" else "")
    _S3.info("%s", _banner("end STAGE 3"))
