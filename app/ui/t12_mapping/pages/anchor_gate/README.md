# anchor_gate page

**URL:** `/t12/<upload_id>/anchors/`

The Stage-1 anchor gate. **Every** upload stops here (nothing auto-advances) — the
`anchor_lock.status` (`AUTO` / `DERIVED` / `GATE` / `NONE`) only decides how the selectors
are pre-filled. Classification (Stage 2) does **not** run until this gate is confirmed —
at gate time only the Stage-1 state exists.

**Reads:**
- `anchor_lock.json` — status, candidates (per R/E/NOI), passing triples, locked anchors (+ split)
- `parse_state.json` — `anchor_rows` (the light {row, description, values} build, to render the selectors)

**Writes:**
- **Re-verify** (POST `action=verify`, via `check_anchors`): **nothing** — a light
  `R − |E| = NOI` check on the picked rows using only `anchor_rows` (no classification, no AI).
- **Confirm** (POST `action=continue`, via `confirm_anchors` → `run_classification`): runs
  **Stage 2** — `classification.json`, `annotated_blocks.json`, `comparison.json`,
  `actual_noi.json`, and flips `anchor_lock.json` to `MANUAL`. The AI failure-diagnosis loop
  runs here only if NOI fails.

**DB:** `Upload.current_step = 'noi_verification'` on Confirm.

**Next:** `noi_verification` (the classification review).

## Behaviour
- Shows the anchor status + explanation, the passing R − |E| = NOI triples, and 3 row
  selectors pre-filled with the locked pick (or the user's picks after a Re-verify).
- **Re-verify** shows the `R − |E| = NOI` verdict green/red without running classification.
  **Confirm** commits and moves to the classification review.
- The check subtracts the expense **magnitude** (`abs`), so vendors that sign expenses
  negative reconcile; a preserved split-pair (kept only if the expense row is unchanged) is
  summed. Live (per-keystroke) re-verify is a future JS enhancement; v1 re-verifies on submit.
