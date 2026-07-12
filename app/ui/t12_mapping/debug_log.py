"""Per-view debug logging for the T12 flow.

Each view receives the full run-state back from the steps, so it logs what it produced —
a one-line summary at INFO (flow visibility), the full detail at DEBUG. Toggle with
`T12_LOG_LEVEL=DEBUG` (and `T12_LOG_FILE=path` to also write to a file).

Loggers are namespaced `t12.<page>`, so the terminal shows exactly which view ran.
"""
import logging
from collections import Counter


def _logger(page):
    return logging.getLogger(f"t12.{page}")


def _fmt(v):
    return f"{v:,.0f}" if isinstance(v, (int, float)) else ("" if v is None else str(v))


def _last(values):
    vals = [x for x in (values or []) if x is not None]
    return vals[-1] if vals else None


def _anchor_table(rows):
    out = [f"{'row':>4}  {'description':<42}  {'total':>14}"]
    for r in rows:
        out.append(f"{r['row']:>4}  {r.get('description', '')[:42]:<42}  {_fmt(_last(r.get('values'))):>14}")
    return "\n".join(out)


def _classified_table(rows):
    out = [f"{'row':>4}  {'description':<34}  {'class':<20} {'section':<8} {'total':>14} {'conf':>5} {'lo'}"]
    for r in rows:
        out.append(f"{r['row']:>4}  {r.get('description', '')[:34]:<34}  {r['class']:<20} "
                   f"{(r.get('section') or ''):<8} {_fmt(_last(r.get('values'))):>14} "
                   f"{(r.get('confidence') or 0):>5.2f} {'!' if r.get('low_confidence') else ''}")
    return "\n".join(out)


def _noi_table(noi):
    out = [f"{'col':<4} {'revenue':>14} {'expense':>14} {'noi(vendor)':>14} {'noi(comp)':>14}  ok"]
    for m in noi.get("months", []):
        out.append(f"{m['col']:<4} {_fmt(m['rev'][1]):>14} {_fmt(m['exp'][1]):>14} "
                   f"{_fmt(m['noi'][0]):>14} {_fmt(m['noi'][1]):>14}  {'ok' if m['noi'][2] else 'XX'}")
    return "\n".join(out)


def log_stage1(state):
    log = _logger("upload")
    lock = state.get("anchor_lock") or {}
    a = lock.get("anchors") or {}
    log.info("stage1 · file=%s · fmt=%s · lock=%s · R=%s E=%s N=%s split=%s",
             (state.get("file") or {}).get("name"), (state.get("format") or {}).get("format"),
             lock.get("status"), a.get("revenue_end_row"), a.get("expense_end_row"),
             a.get("noi_row"), a.get("expense_split_rows"))
    if log.isEnabledFor(logging.DEBUG):
        log.debug("candidates=%s  passing=%s\nanchor rows:\n%s",
                  lock.get("candidates"), lock.get("passing"),
                  _anchor_table(state.get("anchor_rows", [])))


def log_gate(context):
    log = _logger("anchor_gate")
    log.info("gate · status=%s · reconciles=%s · current=%s",
             context.get("status"), context.get("reconciles"), context.get("current"))


def log_classification(state):
    log = _logger("noi_verification")
    cls = state.get("classification") or {}
    noi = cls.get("noi") or {}
    dist = Counter(r["class"] for r in cls.get("classified", []))
    log.info("classify · lock=%s · NOI_pass=%s · low_conf=%d · %s",
             (state.get("anchor_lock") or {}).get("status"), noi.get("overall_pass"),
             len(cls.get("low_confidence_rows") or []),
             " ".join(f"{k}={v}" for k, v in dist.items()))
    if log.isEnabledFor(logging.DEBUG):
        log.debug("NOI verification:\n%s\nclassified rows:\n%s",
                  _noi_table(noi), _classified_table(cls.get("classified", [])))


def log_mapping(mapped):
    log = _logger("data_review")
    s = mapped.get("summary") or {}
    log.info("mapping · %s data rows · %s mapped · %s unmapped",
             s.get("data_rows"), s.get("mapped"), s.get("unmapped"))
