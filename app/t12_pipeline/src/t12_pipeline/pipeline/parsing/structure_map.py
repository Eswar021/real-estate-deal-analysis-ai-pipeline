"""Structure map — the column layout + boundaries a file is parsed against.

- KNOWN formats: `build_known_map` fills columns from the format's fixed layout (no AI).
- UNKNOWN formats: `detect_structure_deterministic` reads the columns straight off the grid
  and the anchor lock is the oracle (if the numbers reconcile, the columns were right); only
  if the lock can't reconcile do we fall back to the AI structure agent, which proposes the
  map that `build_final_map` keeps verbatim (+ arithmetically-validated subsection anchors).

Ported from notebook Modules 8a/8b; deterministic-first routing added (PLANNED_ENHANCEMENTS §2).
"""
import re

from openpyxl.utils import get_column_letter, column_index_from_string

from .cell_grid import grid_row_map, gvalue
from .signals import (detect_value_columns, detect_value_block, CODE_COL, DESC_COL,
                      EMB_DESC_COL, NOCODE_DESC_COL)
from .structure_agent import run_structure_agent

_MIN_MONTH_COLS = 6
KNOWN_FORMATS = ("code_in_a_desc_in_b", "embedded_code_in_a", "no_code")

# the extractor + lock drive the deterministic-first decision (the lock is the oracle);
# CODE_PREFIX_RE (any known code style) is reused to guess whether codes are embedded.
from .extract import CODE_PREFIX_RE, extract_anchor_rows
from .anchor_lock import lock_anchors


_LETTERS = re.compile(r"[A-Za-z]")


def _is_code_column(grid, c, data_start):
    """A column whose data-region cells are mostly bare account codes (digits/punctuation, no
    letters) — e.g. Mesquite's column A '41000-000' with the label sitting in column B. Such a
    column must NOT drive the description, or every row's 'description' is a code and no anchor
    keyword ever matches (the ranker then mis-picks a coincidental gross-rent triple)."""
    tot = code = 0
    for grow in grid["rows"]:
        if data_start and grow["row"] < data_start:
            continue
        v = gvalue(grow, c)
        if isinstance(v, str) and v.strip():
            tot += 1
            if any(ch.isdigit() for ch in v) and not _LETTERS.search(v):
                code += 1
    return tot > 0 and code / tot > 0.5


def _looks_embedded_code(grid, desc_cols_idx, data_start):
    """Majority of description cells in the data region begin with an account code → the
    file embeds codes in the description (so the extractor should strip them)."""
    if not data_start:
        return False
    hit = tot = 0
    for grow in grid["rows"]:
        if grow["row"] < data_start:
            continue
        txt = next((gvalue(grow, c) for c in desc_cols_idx
                    if isinstance(gvalue(grow, c), str) and gvalue(grow, c).strip()), None)
        if txt:
            tot += 1
            if CODE_PREFIX_RE.match(txt):
                hit += 1
    return tot > 0 and hit / tot > 0.5


def detect_structure_deterministic(grid):
    """Deterministic column map for an UNKNOWN file — no AI. Values = the longest contiguous
    numeric run; description = every column left of it (the extractor picks the first non-empty
    text per row, which handles descriptions spread across columns in hierarchical layouts);
    layout rows via the shared detector. R/E/NOI are left NULL for the anchor lock to fill — the
    arithmetic lock is the oracle that says whether these columns were right. Returns the SAME
    shape as `build_known_map` (subsections derived later in Stage 2), or None if no value block
    is found (a grid the deterministic pass can't read → caller falls back to the AI agent)."""
    value_cols = detect_value_block(grid)
    if not value_cols:
        return None
    value_start = value_cols[0]
    month_hdr, data_start = _detect_known_layout(grid, value_cols)
    # every column left of the values is a description column, EXCEPT bare account-code columns
    # (their codes would shadow the real labels the keyword ranker needs)
    desc_cols_idx = [c for c in range(1, value_start) if not _is_code_column(grid, c, data_start)]
    if not desc_cols_idx:
        desc_cols_idx = list(range(1, value_start))
    embedded = _looks_embedded_code(grid, desc_cols_idx, data_start)
    return {
        "description_columns": [get_column_letter(c) for c in desc_cols_idx],
        "value_columns": [get_column_letter(c) for c in value_cols],
        "code_column": None, "code_embedded_in_description": embedded, "code_pattern": None,
        "month_header_row": month_hdr, "data_start_row": data_start,
        "revenue_end_row": None, "expense_end_row": None, "noi_row": None,
        "subsections": [], "validated_subsection_subtotal_rows": [], "subsection_header_rows": [],
    }


def validate_subsections(final, grid):
    """Arithmetic-check each AI subsection: subtotal == sum of the leaf value rows in
    its [header_row, subtotal_row) span that are NOT themselves subtotal rows.
    Summing only non-subtotal leaves makes this correct for nested roll-ups too.
    Returns (per-subsection results, set of VALIDATED subtotal rows)."""
    last_i = column_index_from_string(final["value_columns"][-1])
    rmap   = grid_row_map(grid)
    def cval(r):
        g = rmap.get(r); x = gvalue(g, last_i) if g else None
        return x if isinstance(x, (int, float)) else None

    subs = final["subsections"]
    subtotal_set = {s["subtotal_row"] for s in subs}
    rev_end = final["revenue_end_row"]; data_start = final["data_start_row"]

    results, validated = [], []
    for s in subs:
        R = s["subtotal_row"]; H = s["header_row"]; target = cval(R)
        # span start: the AI header_row if it sits inside this section, else the section start
        sec_start = data_start if (rev_end is None or R <= rev_end) else rev_end + 1
        start = H if (isinstance(H, int) and sec_start <= H < R) else sec_start
        members = [rr for rr in range(start, R)
                   if rr not in subtotal_set and cval(rr) is not None]
        msum = sum(cval(rr) for rr in members)
        ok = target is not None and abs(msum - target) <= 10.0   # flat $10 (sum of leaf members; no %)
        results.append({"name": s["name"], "row": R, "header_row": H, "span": [start, R],
                        "member_rows": members, "member_values": [round(cval(rr), 2) for rr in members],
                        "members": len(members), "sum": round(msum, 2),
                        "target": round(target, 2) if isinstance(target, (int, float)) else target,
                        "ok": ok})
        if ok:
            validated.append(R)
    return results, sorted(set(validated))


def build_final_map(ai_map, grid):
    """Turn the AI structure map into the final_map used downstream: the AI's fields
    verbatim, PLUS the arithmetically-validated subsection anchors. No deterministic
    override — the AI map is trusted; math only validates the subsections.
    Returns (final_map, per-subsection results)."""
    final = ai_map if isinstance(ai_map, dict) else ai_map.model_dump()
    sub_results, validated_rows = validate_subsections(final, grid)
    boundary = {final["revenue_end_row"], final["expense_end_row"], final["noi_row"]} - {None}
    final["subsection_subtotal_rows"]           = sorted({s["subtotal_row"] for s in final["subsections"]} - boundary)
    final["validated_subsection_subtotal_rows"] = [r for r in validated_rows if r not in boundary]
    final["subsection_header_rows"]             = sorted({s["header_row"] for s in final["subsections"]
                                                          if isinstance(s["header_row"], int)} - boundary)
    return final, sub_results


def _detect_known_layout(grid, value_cols):
    """data_start = first row with >=6 numeric value cells; month_header = the last
    row above it that carries text in the value columns (period labels), else the
    row just above data_start."""
    data_start = None
    for grow in grid["rows"]:
        if sum(1 for c in value_cols if isinstance(gvalue(grow, c), (int, float))) >= _MIN_MONTH_COLS:
            data_start = grow["row"]; break
    month_hdr = None
    for grow in grid["rows"]:
        if data_start and grow["row"] >= data_start:
            break
        if sum(1 for c in value_cols if isinstance(gvalue(grow, c), str) and gvalue(grow, c).strip()) >= _MIN_MONTH_COLS:
            month_hdr = grow["row"]
    if month_hdr is None and data_start:
        month_hdr = data_start - 1
    return month_hdr, data_start


def build_known_map(fmt, grid):
    """A minimal 'template' structure map for a KNOWN format — columns come from the
    format's fixed layout, the layout rows are detected, and the R/E/NOI boundaries are
    left for the anchor lock to fill. Lets known files run the SAME dynamic-extract →
    anchor-lock → classify path as unknown files (no AI structure agent needed)."""
    if fmt == "code_in_a_desc_in_b":
        desc_cols, start = [get_column_letter(DESC_COL)], DESC_COL + 1
        code_col, embedded, pattern = get_column_letter(CODE_COL), False, None
    elif fmt == "embedded_code_in_a":
        desc_cols, start = [get_column_letter(EMB_DESC_COL)], EMB_DESC_COL + 1
        code_col, embedded, pattern = None, True, "embedded"
    else:  # no_code
        desc_cols, start = [get_column_letter(NOCODE_DESC_COL)], NOCODE_DESC_COL + 1
        code_col, embedded, pattern = None, False, None
    value_cols = detect_value_columns(grid, start)
    month_hdr, data_start = _detect_known_layout(grid, value_cols)
    return {
        "description_columns": desc_cols,
        "value_columns": [get_column_letter(c) for c in value_cols],
        "code_column": code_col, "code_embedded_in_description": embedded, "code_pattern": pattern,
        "month_header_row": month_hdr, "data_start_row": data_start,
        "revenue_end_row": None, "expense_end_row": None, "noi_row": None,
        "subsections": [], "validated_subsection_subtotal_rows": [], "subsection_header_rows": [],
    }


def run(state):
    """Step: resolve_columns — reads cell_grid, format; writes structure_map, sub_results,
    structure_map_ai, structure_source. KNOWN → template map (no AI). UNKNOWN →
    deterministic-first: read the columns straight off the grid and let the anchor lock decide
    — if any triple reconciles, the columns were right, so we skip the AI. Only a NONE lock (or
    no detectable value block) falls back to the AI structure agent."""
    fmt, grid = state["format"]["format"], state["cell_grid"]
    if fmt in KNOWN_FORMATS:
        return {**state, "structure_map": build_known_map(fmt, grid),
                "sub_results": [], "structure_map_ai": None, "structure_source": "known"}
    det = detect_structure_deterministic(grid)
    if det is not None and lock_anchors(extract_anchor_rows(grid, det), det)["status"] != "NONE":
        return {**state, "structure_map": det, "sub_results": [],
                "structure_map_ai": None, "structure_source": "deterministic"}
    ai = run_structure_agent(grid)
    final_map, sub_results = build_final_map(ai.model_dump(), grid)
    return {**state, "structure_map": final_map, "sub_results": sub_results,
            "structure_map_ai": ai.model_dump(), "structure_source": "ai"}
