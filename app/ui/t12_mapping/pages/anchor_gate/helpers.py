"""
pages/anchor_gate/helpers.py — page-local helpers.

Builds the context for the Stage-1 anchor gate straight from the run-state (Phase D — no
parse_state.json / anchor_lock.json). At gate time neither signal extraction nor
classification has run yet, so the row descriptions + values come from the light Stage-1
`anchor_rows`; the candidates + passing triples + status come from `anchor_lock`.
"""


def int_or_none(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _last_value(r):
    v = r.get("_last_value")
    if v is not None:
        return v
    vals = [x for x in (r.get("values") or []) if x is not None]
    return vals[-1] if vals else None


STATUS_EXPLAIN = {
    "AUTO":    ("success", "One R − E = NOI triple passed — anchors auto-locked. Confirm or adjust."),
    "DERIVED": ("warning", "No NOI keyword matched (e.g. a vendor typo); the NOI row was found by arithmetic (N = R − E). Please confirm."),
    "GATE":    ("warning", "Several R − E = NOI triples pass — genuinely ambiguous. Pick the correct three rows."),
    "NONE":    ("danger",  "No triple reconciled. Pick the revenue / expense / NOI rows manually (or the vendor's numbers are inconsistent)."),
    "MANUAL":  ("warning", "Anchors set manually. Re-verify or confirm to continue."),
}


def build_context(upload, state, chosen=None, reconciles=None, error=None):
    """`chosen` is the user's picks on a Re-verify POST (pre-fills the selectors); `reconciles`
    is that light R − |E| = NOI verdict. On the first GET both are None — the selectors
    pre-fill from the auto-lock and `reconciles` reflects whether the lock found a triple."""
    anchor_lock = state.get("anchor_lock") or {}
    anchor_rows = state.get("anchor_rows", [])
    by = {r["row"]: r for r in anchor_rows}

    def info(rn):
        r = by.get(rn) or {}
        return {"row": rn, "description": r.get("description", ""), "value": _last_value(r)}

    cands = anchor_lock.get("candidates") or {}
    candidates = {t: [info(rn) for rn in cands.get(t, [])] for t in ("revenue", "expense", "noi")}

    passing = []
    for trip in anchor_lock.get("passing", []):
        rr, eu, nr = trip[0], trip[1], trip[2]
        eu = eu if isinstance(eu, list) else [eu]
        passing.append({"revenue": rr, "expense": eu, "noi": nr})

    # pre-fill the selectors with the user's picks (Re-verify) or the locked anchors (GET)
    current = dict(chosen) if chosen else dict(anchor_lock.get("anchors") or {})

    # every value-bearing row — options for the "pick any row" selects
    all_rows = [info(r["row"]) for r in anchor_rows if _last_value(r) is not None]

    status = anchor_lock.get("status") or "NONE"
    tone, explain = STATUS_EXPLAIN.get(status, STATUS_EXPLAIN["NONE"])

    if reconciles is None:                       # GET — no explicit re-verify this request
        reconciles = bool(anchor_lock.get("anchors"))

    return {
        "upload_id":   upload.id,
        "file_name":   (state.get("file") or {}).get("name") or upload.file_name,
        "status":      status,
        "status_tone": tone,
        "status_explain": explain,
        "reconciles":  reconciles,
        "candidates":  candidates,
        "passing":     passing,
        "current":     current,
        "all_rows":    all_rows,
        "error":       error,
    }
