# noi_verification page

**URL:** `/t12/<upload_id>/noi/`

**Reads:**
- `annotated_blocks.json` — current row classifications and flags
- `comparison.json` — pipeline NOI verification result

**Writes** (on every Recompute, so a page refresh shows the latest state):
- `annotated_blocks.json` — corrected with the user's row selections + re-walked statement_side
- `comparison.json` — new NOI comparison against the corrected data

**DB:** updates `Upload.current_step='noi_verification'` (or `'data_review'` on Save & Continue, future)

**Next:** `data_review` (on Save & Continue, future)

## NOI pass/fail logic (helpers.ui_pass)

1. `comparison["overall_pass"]` — pipeline's NOI match (catches wrong NOI row selection)
2. `comparison["total_revenue_check"]["match"]` — catches wrong revenue row selection (vendor_egi comes from the flagged is_total_revenue row, so the check is row-dependent)
3. Expense row cross-check — compares `is_total_expense` flagged row value against `total_expense_check["row_method"]` (expense data sum). Threshold mirrors the pipeline's `STRICT` flag via `comparison["tolerance_used"]`.

The expense cross-check is needed because the pipeline's `total_expense_check` uses `EGI − NOI` (not the flagged row), so changing the expense row wouldn't otherwise affect PASS/FAIL.
