# data_review page

**URL:** `/t12/<upload_id>/review/`

**Reads:** the **run-state** via `bridge.get_state(id, with_grid=False)`:
- `state.mapping` — Stage 3 output: every data row with `mapping`, `ai_suggested_mapping`, `final_mapping` (user override), `flip_sign`
- `state.classification.noi.months` — Stage 2's verified NOI result. **The whole bottom summary is this** — the page does not compute NOI itself.

**Writes** (on every row update POST, via `run_step(id, "stage3_update_mapping")`):
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

Per-row boolean. When True, the row's displayed values are flipped (used when a vendor entered a
vacancy as a positive under revenue, or a credit as a negative under expense). Manual only — no
auto-detection. It is an **output/sign-convention annotation**: it flips the row's values in the
table and is stored for the future export. It does **not** move the summary — the vendor's NOI is
a fact locked at Stage 1 and verified at Stage 2, and a sign convention chosen afterwards can't
restate it.

## Bottom summary rows

`helpers.compute_summary(noi_months, column_headers)` is a **presenter over Stage 2's verified
NOI**, not a calculation:

- **Net Rental Income** — `months[i]["rev"][1]` (our computed revenue)
- **Calculated NOI** — `months[i]["noi"][1]` (our computed NOI: `revenue − |expense|`, capex excluded)
- **Original NOI** — `months[i]["noi"][0]` (vendor-reported, off the locked NOI row)
- **NOI Difference** — Calculated − Original; red iff `months[i]["noi"][2] is False` (Stage 2's own
  per-month flag, i.e. the pipeline's $10 `NOI_TOLERANCE`)

⚠ **Do not re-derive these from the mapped rows.** The page used to, and it drifted: it summed
`revenue − expense` where the pipeline sums `revenue − |expense|`, so a vendor signing expenses
negative (Chateau in the Woods) showed a $730k difference on a file Stage 2 had passed. It also
tested `!= 0`, flagging cents of rounding drift as failure. Mapping only assigns categories — it
cannot move the money, so there is nothing here for a second opinion to catch.

Not yet covered (need meeting-transcript context):
- "Items added/excluded from NOI"
- "Final Difference"
