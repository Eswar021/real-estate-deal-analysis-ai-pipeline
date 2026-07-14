"""Stage 1 — Anchor Lock (arithmetic-first: R − |E| = NOI decides).

The MATH finds the triples FIRST, over *all* value-bearing rows — not a keyword shortlist.
We hypothesise (R above N), the pair implies the expense magnitude |E| = R_total − N_total,
and we hash-look-up an expense unit carrying that total (the "3SUM via hashing" / hash-join
trick — `O(n²)` probes instead of the `O(n³)` all-triples test), then verify R − |E| = NOI
month-by-month. Keywords only RANK the survivors (they no longer GATE which rows qualify), so
a novel vendor term still locks. One clear winner → AUTO (or DERIVED if its NOI row carried no
NOI keyword); a genuine tie → GATE; nothing reconciles → NONE.

The `abs()` on the expense covers both sign conventions (expenses stored positive or negative).
See `docs/build/PLANNED_ENHANCEMENTS.md` §1 for the design.
"""
import json

from t12_pipeline.config.paths import ANCHOR_KEYWORDS_PATH


def load_anchor_keywords(path=ANCHOR_KEYWORDS_PATH):
    with open(path) as f:
        return json.load(f)


ANCHOR_KEYWORDS = load_anchor_keywords()

_ATOL, _AFRAC, _MINCOLS = 1.0, 0.0, 6        # flat $1 tolerance; >=6 month columns
# Flat $1, not a percentage: the anchors are 3 single grand-total rows, so the only error is
# the vendor rounding each to whole dollars (observed max across 24 files: exactly $1). A % would
# scale to thousands on a $2M total and let a coincidental triple slip through the arithmetic.


def _mvals(row):
    """Per-value-column values of a row (numeric or None), aligned to value_columns."""
    return [v if isinstance(v, (int, float)) else None for v in row.get("values", [])]


def _ncount(vals):
    return sum(1 for v in vals if isinstance(v, (int, float)))


def _amatch(a, c):
    return a is not None and c is not None and abs(a - c) <= max(_ATOL, abs(a) * _AFRAC)


def _hits(rows, markers, exclusions):
    out = []
    for r in rows:
        d = r["description"].strip().lower()
        if any(x in d for x in exclusions):
            continue
        if any(m in d for m in markers) and _ncount(_mvals(r)) >= _MINCOLS:
            out.append(r["row"])
    return out


def nominate_anchors(rows, kw, ai_rows):
    """Per anchor type: grand-marker rows (intermediates only if no grand fires),
    minus exclusions, requiring >=6 numeric month values; unioned with the AI's rows."""
    cands = {}
    for t in ("revenue", "expense", "noi"):
        cfg = kw[t]
        c = _hits(rows, cfg["grand_markers"], cfg.get("exclusions", []))
        if not c:
            c = _hits(rows, cfg.get("intermediate_markers", []), cfg.get("exclusions", []))
        if ai_rows.get(t):
            c = sorted(set(c) | {ai_rows[t]})
        cands[t] = sorted(set(c))
    return cands


def _total(vals):
    """The row's annual-total column — its last numeric value. Used as the hash key: the
    grand total is the most distinctive number a row carries (collisions are verified away)."""
    nums = [v for v in vals if isinstance(v, (int, float))]
    return nums[-1] if nums else None


def _expense_pairs(rows, kw):
    """Split-pair expense units (controllable + non-controllable) from the keyword pairs.
    These are the only pairs we index — a full all-pairs search would invent phantom sums;
    the split pattern has standard wording, so the keyword pairs are the safe bounded set."""
    pairs, seen = [], set()
    for pm in kw["expense"].get("split_pair_markers", {}).get("pairs", []):
        legs = []
        for m in pm:
            legs.append([r["row"] for r in rows
                         if m in r["description"].strip().lower() and _ncount(_mvals(r)) >= _MINCOLS])
        for a in legs[0]:
            for b in legs[1]:
                if a != b:
                    k = tuple(sorted([a, b]))
                    if k not in seen:
                        seen.add(k); pairs.append(list(k))
    return pairs


def _row_matches(desc, markers, exclusions):
    d = (desc or "").strip().lower()
    if any(x in d for x in exclusions):
        return False
    return any(m in d for m in markers)


def _kw_score(rr, eunit, nr, byrow, kw):
    """How many of the three anchors carry a known keyword (0–3). Arithmetic-first: keywords
    only RANK the reconciling triples, they no longer gate which rows are candidates."""
    def side(t, row):
        cfg = kw[t]
        return _row_matches(byrow[row]["description"],
                            cfg["grand_markers"] + cfg.get("intermediate_markers", []),
                            cfg.get("exclusions", []))
    r_ok = side("revenue", rr)
    e_ok = any(side("expense", e) for e in eunit)
    n_ok = _row_matches(byrow[nr]["description"], kw["noi"]["grand_markers"], kw["noi"].get("exclusions", []))
    return int(r_ok) + int(e_ok) + int(n_ok)


def _triple_holds(rrow, eunit, nrow, byrow):
    rv = _mvals(byrow[rrow]); nv = _mvals(byrow[nrow])
    n = len(rv)
    ev = [None] * n
    for er in eunit:
        for i, x in enumerate(_mvals(byrow[er])):
            if isinstance(x, (int, float)):
                ev[i] = (ev[i] or 0.0) + x
    matched = 0
    for i in range(n):
        if rv[i] is None or ev[i] is None or nv[i] is None:
            continue
        # NOI = revenue − expense MAGNITUDE. abs() covers both sign conventions: vendors
        # who store expenses positive (rv − ev) and vendors who store them negative
        # (rv − |ev| = rv + ev). Without it, negative-signed expenses never reconcile.
        if not _amatch(nv[i], rv[i] - abs(ev[i])):
            return False
        matched += 1
    return matched >= _MINCOLS


def lock_anchors(rows, final_map):
    """Arithmetic-first R − |E| = NOI lock. The MATH finds every reconciling triple over ALL
    value-bearing rows (not a keyword shortlist); keywords only RANK the survivors. Exactly one
    clear winner → AUTO / DERIVED; a genuine tie → GATE; nothing reconciles → NONE. Returns
    dict(status, method, anchors, passing, candidates). status ∈ {AUTO, DERIVED, GATE, NONE};
    `anchors` gives revenue_end_row / expense_end_row / noi_row (expense boundary = bottom-most
    of a split pair).

    hash-join trick: we never know which rows are R/E/NOI up front, so we fix (R above N),
    the pair implies |E| = R_total − N_total, and we hash-look-up an expense unit with that
    total — O(n²) probes instead of the O(n³) all-triples test. See PLANNED_ENHANCEMENTS §1."""
    from collections import defaultdict

    byrow = {r["row"]: r for r in rows}
    vrows = [r for r in rows if _ncount(_mvals(r)) >= _MINCOLS]

    # keyword nominations are no longer a gate — kept only for the ranker + the gate's shortlist
    ai_rows = {"revenue": final_map.get("revenue_end_row"),
               "expense": final_map.get("expense_end_row"),
               "noi": final_map.get("noi_row")}
    cands = nominate_anchors(rows, ANCHOR_KEYWORDS, ai_rows)

    # index every expense unit (each single row + each keyword split-pair) by its |annual total|
    units = [[r["row"]] for r in vrows] + _expense_pairs(vrows, ANCHOR_KEYWORDS)
    by_abs_total = defaultdict(list)
    for u in units:
        legs = [_total(_mvals(byrow[e])) for e in u]
        if all(t is not None for t in legs):
            by_abs_total[round(sum(abs(t) for t in legs))].append(u)

    # hash-join: for each (R above N), the implied |E| = R_total − N_total; look that unit up
    passing, seen = [], set()
    for R in vrows:
        rt = _total(_mvals(R))
        if rt is None:
            continue
        for N in vrows:
            if N["row"] <= R["row"]:
                continue
            nt = _total(_mvals(N))
            if nt is None or nt >= rt:                    # NOI sits below revenue in value
                continue
            target = round(rt - nt)
            for d in (-1, 0, 1):                          # ±$1 rounding-boundary guard
                for eu in by_abs_total.get(target + d, []):
                    if R["row"] in eu or N["row"] in eu:
                        continue
                    if not (R["row"] < min(eu) and max(eu) < N["row"]):
                        continue
                    key = (R["row"], tuple(eu), N["row"])
                    if key in seen or not _triple_holds(R["row"], eu, N["row"], byrow):
                        continue
                    seen.add(key)
                    passing.append((R["row"], eu, N["row"]))

    def _pack(t):
        rr, eu, nr = t
        return {"revenue_end_row": rr, "expense_end_row": max(eu), "noi_row": nr,
                "expense_split_rows": (eu if len(eu) > 1 else None)}

    if not passing:
        return {"status": "NONE", "method": None, "anchors": None,
                "passing": [], "candidates": cands}

    def _rev_total(t):
        return abs(_total(_mvals(byrow[t[0]])) or 0)

    def _score(t):
        # keyword-confirmed first, then grandest revenue, then bottom-most rows
        return (_kw_score(t[0], t[1], t[2], byrow, ANCHOR_KEYWORDS), _rev_total(t), t[0], max(t[1]), t[2])

    passing.sort(key=_score, reverse=True)
    best = passing[0]
    bk, brev = _kw_score(best[0], best[1], best[2], byrow, ANCHOR_KEYWORDS), _rev_total(best)

    # The CONTENDERS are the winner plus any triple that TIES it on both keyword-confirmation
    # and revenue magnitude — a genuine either/or. Coincidental sub-arithmetic triples (a
    # subsection that happens to reconcile, an intermediate net) rank below and drop out, so
    # the gate isn't spammed with them. Several contenders → GATE; one → AUTO/DERIVED.
    contenders = [best] + [t for t in passing[1:]
                           if _kw_score(t[0], t[1], t[2], byrow, ANCHOR_KEYWORDS) == bk
                           and _amatch(_rev_total(t), brev)]
    if len(contenders) > 1:
        return {"status": "GATE", "method": "manual", "anchors": _pack(best),
                "passing": contenders, "candidates": cands}

    # one clear winner: AUTO if its NOI row carries a NOI keyword, else DERIVED (the triple
    # reconciled but no NOI keyword matched — the NOI row was found purely by the arithmetic).
    n_ok = _row_matches(byrow[best[2]]["description"],
                        ANCHOR_KEYWORDS["noi"]["grand_markers"], ANCHOR_KEYWORDS["noi"].get("exclusions", []))
    status = "AUTO" if n_ok else "DERIVED"
    return {"status": status, "method": "auto" if n_ok else "derived-matched",
            "anchors": _pack(best), "passing": contenders, "candidates": cands}


def run(state):
    """Step: lock_anchors — reads anchor_rows, structure_map; writes anchor_lock and the
    locked R/E/NOI rows (+ any expense split) into structure_map."""
    lock = lock_anchors(state["anchor_rows"], state["structure_map"])
    fm = state["structure_map"]
    if lock["anchors"]:
        a = lock["anchors"]
        fm = {**fm, "revenue_end_row": a["revenue_end_row"], "expense_end_row": a["expense_end_row"],
              "noi_row": a["noi_row"], "expense_split_rows": a.get("expense_split_rows")}
    return {**state, "anchor_lock": lock, "structure_map": fm}


def run_check(state):
    """Step: check_anchors — light R − |E| = NOI re-verify of state['anchors'] against the
    Stage-1 anchor_rows (keeps the auto split only if the expense row is unchanged).
    writes reconcile."""
    locked = (state.get("anchor_lock") or {}).get("anchors") or {}
    picks  = state.get("anchors") or {}
    exp    = picks.get("expense_end_row")
    split  = locked.get("expense_split_rows") if exp == locked.get("expense_end_row") else None
    eunit  = split or [exp]
    rc = reconcile_triple(state.get("anchor_rows", []),
                          picks.get("revenue_end_row"), eunit, picks.get("noi_row"))
    return {**state, "reconcile": rc}


def reconcile_triple(rows, revenue_row, expense_unit, noi_row):
    """Light per-month `R − |E| = NOI` check for one specific triple — the anchor gate's
    re-verify. `rows` is the Stage-1 anchor_rows ({row, description, values}); NO signals,
    NO classification. `expense_unit` is a list (a single row, or a split pair). Returns
    {reconciles, matched, months:[{i, revenue, expense, noi, computed, match}]}."""
    byrow = {r["row"]: r for r in rows}
    eu = [e for e in (expense_unit or []) if e is not None]
    if revenue_row not in byrow or noi_row not in byrow or not eu or any(e not in byrow for e in eu):
        return {"reconciles": False, "matched": 0, "months": []}
    rv, nv = _mvals(byrow[revenue_row]), _mvals(byrow[noi_row])
    ev = [None] * len(rv)
    for er in eu:
        for i, x in enumerate(_mvals(byrow[er])):
            if isinstance(x, (int, float)):
                ev[i] = (ev[i] or 0.0) + x
    months, matched, all_ok = [], 0, True
    for i in range(len(rv)):
        if rv[i] is None or ev[i] is None or nv[i] is None:
            continue
        calc = rv[i] - abs(ev[i])
        ok = _amatch(nv[i], calc)
        matched += ok
        all_ok = all_ok and ok
        months.append({"i": i, "revenue": rv[i], "expense": ev[i], "noi": nv[i],
                       "computed": round(calc, 2), "match": ok})
    return {"reconciles": all_ok and matched >= _MINCOLS, "matched": matched, "months": months}


def apply_anchor_overrides(classified, final_map):
    """Arithmetic-verified facts OVERRIDE the classifier score: the locked anchors and
    the arithmetically-validated subsection subtotals get their class forced."""
    facts = {}
    if final_map.get("noi_row"):
        facts[final_map["noi_row"]] = "COMPUTED_METRIC"
    for b in (final_map.get("revenue_end_row"), final_map.get("expense_end_row")):
        if isinstance(b, int):
            facts[b] = "SECTION_SUBTOTAL"
    for s in final_map.get("validated_subsection_subtotal_rows", []):
        facts.setdefault(s, "SUBSECTION_SUBTOTAL")
    out = []
    for r in classified:
        r2 = dict(r)
        if r["row"] in facts:
            r2["class"] = facts[r["row"]]
        out.append(r2)
    return out
