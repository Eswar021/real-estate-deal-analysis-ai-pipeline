# data_review page

**URL:** `/t12/<upload_id>/review/`

**Reads:** the **run-state** via `bridge.get_state(id, with_grid=False)`:
- `state.mapping` — Stage 3 output: every data row with `mapping`, `ai_suggested_mapping`, `final_mapping` (user override), `flip_sign`
- `state.classification.noi` — the per-month NOI verification, for the "Original NOI" summary row

**Writes** (on every row update POST, via `bridge.save_mapping`):
- `state.mapping` — patches `final_mapping` and `flip_sign` on the targeted row, preserving the original `mapping` and `ai_suggested_mapping` for audit

**DB:** updates `Upload.current_step='data_review'`

**Next:** analytics page (future)

## Three mapping layers

A row's "effective category" is computed in `helpers.effective_mapping_of()`:

```
final_mapping  ?? mapping  ?? ai_suggested_mapping  ?? None
```

So the user's override always wins, then the rulebook hit, then the AI suggestion. Original fields are never overwritten — clearing the dropdown sets `final_mapping = None` and the original recommendation reappears.

## Flip-sign

Per-row boolean. When True, the row's values' signs are flipped (used when a vendor entered a vacancy as a positive number under revenue, or a credit as a negative under expense). Manual only — no auto-detection.

## Bottom summary rows

All derived in `helpers.compute_summary()`:

- **Net Rental Income** — sum of revenue-side data rows per month (with flip-sign applied)
- **Calculated NOI** — revenue rows minus expense rows per month (capex skipped)
- **Original NOI** — from `actual_noi.json` `noi.by_month` (vendor-reported)
- **NOI Difference** — Calculated − Original per month

Not yet covered (need meeting-transcript context):
- "Items added/excluded from NOI"
- "Final Difference"
