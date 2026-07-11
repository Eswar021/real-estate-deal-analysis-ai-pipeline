"""Module 9 — Dynamic signal extraction driven by the structure map.

Emits the per-row feature vector — the RAW SIGNAL POOL the classifier scores — plus
the raw monthly `values`. column_depth carries the TREE hierarchy; whitespace_depth
carries it for FLAT layouts. The AI subsection anchors (is_subsection_subtotal /
is_subsection_header) are kept as FACTS for the override layer, not scored.

One extractor for ALL formats — known files supply a template map, unknown files the
AI map. Ported verbatim from notebook Module 9.
"""
import re

from openpyxl.utils import column_index_from_string, get_column_letter

from .cell_grid import gcell, gvalue
from .signals import (has_total_keyword, total_keyword_hit, is_metric,
                      apply_arithmetic, METRIC_KEYWORDS)

# strip a leading account code of any known style (dot / colon / mri / 5-digit / dash)
CODE_PREFIX_RE = re.compile(
    r"^\s*(?:\d{4}\.\d+|\d{4}:|\d-\d{4}-\d+|\d{5}-\d+|\d{4}\s*-\s*\d*\s*-?)\s*"
)


def _desc_from_columns(grow, desc_cols_idx):
    """First non-empty text cell scanning the description columns left-to-right.
    Returns (raw_text, depth_index) or (None, None)."""
    for depth, c in enumerate(desc_cols_idx):
        v = gvalue(grow, c)
        if isinstance(v, str) and v.strip():
            return v, depth
    return None, None


def extract_row_signals_dynamic(grid, final_map):
    """Per-row feature vector driven by final_map: the raw signal pool + monthly values."""
    max_row = grid["max_row"]
    desc_cols_idx = [column_index_from_string(c) for c in final_map["description_columns"]]
    value_cols    = [column_index_from_string(c) for c in final_map["value_columns"]]
    embedded      = final_map["code_embedded_in_description"]
    month_hdr     = final_map.get("month_header_row")
    # anchors from the AI's arithmetic-validated subsection hierarchy — kept as FACTS
    # (a later override layer may use them); the classifier does NOT score them.
    sub_subtotals = set(final_map.get("validated_subsection_subtotal_rows",
                                      final_map.get("subsection_subtotal_rows", [])))
    sub_headers   = set(final_map.get("subsection_header_rows", []))
    rows = []

    # ── pass 1 ──
    for grow in grid["rows"]:
        r = grow["row"]
        raw, depth = _desc_from_columns(grow, desc_cols_idx)
        raw = raw if raw is not None else ""
        desc = CODE_PREFIX_RE.sub("", raw).strip() if embedded else raw.strip()

        raw_vals = [gvalue(grow, c) for c in value_cols]                 # per value-column
        numeric  = [v for v in raw_vals if isinstance(v, (int, float))]
        if not desc and not numeric:
            continue

        desc_col = desc_cols_idx[depth] if depth is not None else desc_cols_idx[0]
        desc_cell = gcell(grow, desc_col)
        is_bold = bool(desc_cell["bold"]) if desc_cell else False
        has_formula = any((gcell(grow, c) or {}).get("formula") for c in value_cols)
        # accountant's sum-line: a top border on the label cell or any value cell
        top_border = bool(desc_cell and desc_cell.get("border_top")) or \
                     any((gcell(grow, c) or {}).get("border_top") for c in value_cols)
        letters = [ch for ch in desc if ch.isalpha()]

        # ── provenance: WHY each signal is what it is (for logging / client explain) ──
        code_m = CODE_PREFIX_RE.match(raw) if embedded else None
        border_cells  = [get_column_letter(c) for c in [desc_col, *value_cols]
                         if (gcell(grow, c) or {}).get("border_top")]
        formula_cells = {get_column_letter(c): (gcell(grow, c) or {}).get("formula")
                         for c in value_cols if (gcell(grow, c) or {}).get("formula")}
        tk_hit = total_keyword_hit(desc)
        mk_hit = next((k for k in METRIC_KEYWORDS if k in desc.lower()), None)

        rows.append({
            "row":                    r,
            "description":            desc,
            "has_values":             len(numeric) > 0,
            "value_count":            len(numeric),
            "values":                 [round(v, 2) if isinstance(v, (int, float)) else None
                                       for v in raw_vals],           # 12 months + total, aligned to value_columns
            "is_bold":                is_bold,
            "total_keyword":          has_total_keyword(desc),
            "is_metric":              is_metric(desc),
            "has_formula":            bool(has_formula),
            "top_border":             bool(top_border),
            "whitespace_depth":       len(raw) - len(raw.lstrip()),
            "column_depth":           depth if depth is not None else 0,
            "all_caps":               bool(letters) and all(ch.isupper() for ch in letters),
            "position_in_file":       round(r / max_row, 2),
            "in_metadata_band":       month_hdr is not None and r <= month_hdr,
            "is_subsection_subtotal": r in sub_subtotals,
            "is_subsection_header":   r in sub_headers,
            "signal_evidence": {
                "raw_description":    raw,
                "stripped_code":      code_m.group(0).strip() if (code_m and code_m.group(0).strip()) else None,
                "desc_column":        get_column_letter(desc_col),
                "leading_spaces":     len(raw) - len(raw.lstrip()),
                "bold_cell":          get_column_letter(desc_col) if is_bold else None,
                "total_keyword_hit":  tk_hit,
                "metric_keyword_hit": mk_hit,
                "subtotal_marked_by": [n for n, on in (("bold", is_bold), ("total_keyword", bool(tk_hit))) if on],
                "top_border_cells":   border_cells,
                "formula_cells":      formula_cells,
            },
            "_last_value":            numeric[-1] if numeric else None,
        })

    apply_arithmetic(rows)
    return rows
