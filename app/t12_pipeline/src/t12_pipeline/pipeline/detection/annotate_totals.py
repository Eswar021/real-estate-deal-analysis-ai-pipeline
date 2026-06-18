"""
annotate_totals.py — Stage 1b

Adds three boolean flags to every row in the block-detection JSON:
  - is_total_revenue  : the grand income/revenue subtotal row
  - is_total_expense  : the grand operating expense subtotal row
  - is_noi            : the Net Operating Income subtotal row

These flags are used by the UI so users can locate and correct
the key structural rows. All non-subtotal rows get all three as false.

Usage:
    python src/pipeline/1_mapping/annotate_totals.py

Reads:
    manifest["l1"]["paths"]["block_detection_dir"]  (per-file JSON)

Writes:
    manifest["l1"]["paths"]["annotated_blocks_dir"] (per-file JSON with flags)

Does not call an LLM.
"""

import json
import re
from pathlib import Path

GRAND_INCOME_TOTAL_MARKERS = frozenset({
    "total income",
    "total revenue",
    "effective gross income",
    "total operating revenues",
})

GRAND_NOI_MARKERS = frozenset({
    "net operating income",
})

GRAND_EXPENSE_MARKERS = frozenset({
    "total expenses",
    "total operating expenses",
    "total controllable expenses",
    "total expense",
    "total operating costs",
})

_NOI_WORD_RE = re.compile(r"\bnet operating income\b", re.IGNORECASE)


def _matches_income(desc_lower: str) -> bool:
    return any(marker in desc_lower for marker in GRAND_INCOME_TOTAL_MARKERS)


def _matches_noi(desc_lower: str) -> bool:
    return bool(_NOI_WORD_RE.search(desc_lower))


def _matches_expense(desc_lower: str) -> bool:
    return any(marker in desc_lower for marker in GRAND_EXPENSE_MARKERS)


def _dedup_flag_to_bottom_with_values(rows: list, flag_name: str) -> None:
    """
    When multiple subtotal rows are flagged with `flag_name`, keep only the
    BOTTOM-most one that has numeric values. If none have values, keep the
    bottom-most one anyway.

    This matches what compute_noi._find_primary_flagged_row picks, so the UI
    dropdown and the NOI calculation agree on which row is "the" NOI / revenue.

    Without this, files with a summary row at the top (no values) + the real
    subtotal at the bottom both get flagged, and downstream consumers
    disagree on which one to use (causing PASS-on-load + FAIL-on-Recompute).
    """
    indices = [i for i, r in enumerate(rows)
               if r.get(flag_name) and r.get("type") == "subtotal"]
    if len(indices) <= 1:
        return  # 0 or 1 match — nothing to dedup

    # Find the last index whose row has at least one numeric value
    last_with_values = None
    for i in indices:
        vals = rows[i].get("values") or []
        if any(isinstance(v, (int, float)) for v in vals):
            last_with_values = i

    keeper = last_with_values if last_with_values is not None else indices[-1]
    for i in indices:
        if i != keeper:
            rows[i][flag_name] = False


def annotate_file(entry: dict) -> dict:
    rows = entry.get("rows", [])

    # First pass: keyword-based flags. Every matching subtotal row gets the flag;
    # dedup runs after this loop.
    for i, row in enumerate(rows):
        if row.get("type") != "subtotal":
            row["is_total_revenue"] = False
            row["is_total_expense"] = False
            row["is_noi"] = False
            continue

        desc_lower = (row.get("description") or "").lower()
        row["is_total_revenue"] = _matches_income(desc_lower)
        row["is_noi"] = _matches_noi(desc_lower)
        row["is_total_expense"] = _matches_expense(desc_lower)

    # Dedup is_noi and is_total_revenue BEFORE the expense dedup runs —
    # the expense dedup needs `first_noi` to be the *real* NOI row (the one
    # with values), not a top-of-page summary row.
    _dedup_flag_to_bottom_with_values(rows, "is_noi")
    _dedup_flag_to_bottom_with_values(rows, "is_total_revenue")

    # Now compute the helper indices for expense dedup. After the dedup above,
    # noi_indices has at most one entry.
    noi_indices = [i for i, r in enumerate(rows)
                   if r.get("is_noi") and r.get("type") == "subtotal"]
    expense_keyword_indices = [i for i, r in enumerate(rows)
                                if r.get("is_total_expense") and r.get("type") == "subtotal"]
    last_expense_subtotal_idx = None
    for i, r in enumerate(rows):
        if r.get("type") == "subtotal" and r.get("statement_side") == "expense":
            last_expense_subtotal_idx = i

    first_noi = noi_indices[0] if noi_indices else len(rows)

    if len(expense_keyword_indices) > 1:
        # Multiple keyword matches — keep only the last one before NOI row.
        # Intermediate subtotals (e.g. "total controllable expenses") are not the grand total.
        valid = [i for i in expense_keyword_indices if i < first_noi]
        for i in expense_keyword_indices:
            rows[i]["is_total_expense"] = False
        if valid:
            rows[valid[-1]]["is_total_expense"] = True
    elif not expense_keyword_indices and last_expense_subtotal_idx is not None:
        # Fallback: no keyword match — use the last expense subtotal before NOI.
        if last_expense_subtotal_idx < first_noi:
            rows[last_expense_subtotal_idx]["is_total_expense"] = True

    return entry


def annotate_all(block_detection_dir: Path, annotated_blocks_dir: Path) -> None:
    annotated_blocks_dir.mkdir(parents=True, exist_ok=True)
    input_files = sorted(block_detection_dir.glob("*.json"))

    if not input_files:
        raise FileNotFoundError(f"No block-detection JSON files in {block_detection_dir}")

    for path in input_files:
        with open(path, "r") as f:
            entry = json.load(f)

        annotate_file(entry)

        out_path = annotated_blocks_dir / path.name
        with open(out_path, "w") as f:
            json.dump(entry, f, indent=2)

        print(f"  Annotated: {path.name}")


if __name__ == "__main__":
    from t12_pipeline.config.paths import MANIFEST_PATH
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"No manifest at {MANIFEST_PATH}. Run Stage 0 first."
        )

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    block_detection_dir = Path(manifest["l1"]["paths"]["block_detection_dir"])
    annotated_blocks_dir = Path(manifest["l1"]["paths"]["annotated_blocks_dir"])

    annotate_all(block_detection_dir, annotated_blocks_dir)
