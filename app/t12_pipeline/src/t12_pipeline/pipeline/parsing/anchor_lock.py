"""Stage 1 — Anchor Lock (R − E = N arithmetic decides).

Nominate candidate R / E / NOI rows (keywords from anchor_keywords.json UNION the
AI's proposed rows), then let the month-by-month R − E = N arithmetic pick the real
triple. Exactly one positionally-coherent passing triple auto-locks; zero/multiple
→ gate; no NOI keyword match → derive N = R − E and find the matching row. Keywords
only NOMINATE; the math DECIDES. Replaces the keyword state machine and kills the
after-debt keyword collision (that row misses R−E=N by the debt service).

Ported verbatim from the notebook anchor-lock cell (keywords loaded from config).
"""
import json

from t12_pipeline.config.paths import ANCHOR_KEYWORDS_PATH


def load_anchor_keywords(path=ANCHOR_KEYWORDS_PATH):
    with open(path) as f:
        return json.load(f)


ANCHOR_KEYWORDS = load_anchor_keywords()

_ATOL, _AFRAC, _MINCOLS = 1.0, 0.005, 6      # tolerance max($1, 0.5%); >=6 month columns


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


def _expense_units(rows, kw, exp_cands):
    """Expense candidates as single rows PLUS split-pair sums (controllable + non-)."""
    units = [[e] for e in exp_cands]
    for pair in kw["expense"].get("split_pair_markers", {}).get("pairs", []):
        legs = []
        for m in pair:
            legs.append([r["row"] for r in rows
                         if m in r["description"].strip().lower() and _ncount(_mvals(r)) >= _MINCOLS])
        for a in legs[0]:
            for b in legs[1]:
                if a != b:
                    units.append(sorted([a, b]))
    seen, out = set(), []
    for u in units:
        k = tuple(u)
        if k not in seen:
            seen.add(k); out.append(u)
    return out


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
    """Nominate → triple-test → lock. Returns dict(status, method, anchors, passing,
    candidates). status ∈ {AUTO, GATE, DERIVED, NONE}. `anchors` gives revenue_end_row
    / expense_end_row / noi_row (expense boundary = bottom-most of a split pair)."""
    byrow = {r["row"]: r for r in rows}
    ai_rows = {"revenue": final_map.get("revenue_end_row"),
               "expense": final_map.get("expense_end_row"),
               "noi": final_map.get("noi_row")}
    cands = nominate_anchors(rows, ANCHOR_KEYWORDS, ai_rows)
    eunits = _expense_units(rows, ANCHOR_KEYWORDS, cands["expense"])

    passing = []
    for rr in cands["revenue"]:
        for eu in eunits:
            if rr in eu:
                continue
            for nr in cands["noi"]:
                if nr == rr or nr in eu:
                    continue
                if _triple_holds(rr, eu, nr, byrow):
                    passing.append((rr, eu, nr))

    coherent = [(rr, eu, nr) for (rr, eu, nr) in passing if rr < min(eu) and max(eu) < nr]
    pool = coherent or passing

    def _pack(t):
        rr, eu, nr = t
        return {"revenue_end_row": rr, "expense_end_row": max(eu), "noi_row": nr,
                "expense_split_rows": (eu if len(eu) > 1 else None)}

    if len(pool) == 1:
        return {"status": "AUTO", "method": "auto", "anchors": _pack(pool[0]),
                "passing": pool, "candidates": cands}
    if len(pool) > 1:
        # bottom-most per anchor: the grand total is the LAST total of its kind
        best = max(pool, key=lambda t: (t[0], max(t[1]), t[2]))
        return {"status": "GATE", "method": "manual", "anchors": _pack(best),
                "passing": pool, "candidates": cands}

    # zero passing (no NOI keyword matched, e.g. a vendor typo "Net Operationg Income",
    # or no NOI row at all) → DERIVE N = R − E and find the row whose values match it.
    dmatched = []
    for rr in cands["revenue"]:
        rv = _mvals(byrow[rr])
        for eu in eunits:
            if rr in eu:
                continue
            ev = [None] * len(rv)
            for er in eu:
                for i, x in enumerate(_mvals(byrow[er])):
                    if isinstance(x, (int, float)):
                        ev[i] = (ev[i] or 0.0) + x
            derived = [(rv[i] - abs(ev[i])) if (rv[i] is not None and ev[i] is not None) else None
                       for i in range(len(rv))]
            if sum(1 for v in derived if v is not None) < _MINCOLS:
                continue
            for r in rows:
                nr = r["row"]
                if nr == rr or nr in eu or not (rr < min(eu) < nr):
                    continue
                cv = _mvals(byrow[nr])
                mm, ok = 0, True
                for i in range(len(derived)):
                    if derived[i] is None or cv[i] is None:
                        continue
                    if not _amatch(derived[i], cv[i]):
                        ok = False; break
                    mm += 1
                if ok and mm >= _MINCOLS:
                    dmatched.append((rr, eu, nr))
    if dmatched:
        best = max(dmatched, key=lambda t: (t[0], max(t[1]), t[2]))
        return {"status": "DERIVED", "method": "derived-matched", "anchors": _pack(best),
                "passing": dmatched, "candidates": cands}
    return {"status": "NONE", "method": None, "anchors": None,
            "passing": [], "candidates": cands}


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
