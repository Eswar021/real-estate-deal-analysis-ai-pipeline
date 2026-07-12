# anchor_gate page

**URL:** `/t12/<upload_id>/anchors/`

The Stage-1 anchor gate. Shown by `upload` only when the R − E = NOI lock is
**ambiguous** — `anchor_lock.status` in `GATE` / `DERIVED` / `NONE`. For a clean
`AUTO` lock the upload page skips straight to `/noi/`.

**Reads:**
- `anchor_lock.json` — status, candidates (per R/E/NOI), passing triples
- `annotated_blocks.json` — row descriptions + values (to render the candidates)
- `comparison.json` — current reconcile verdict (`overall_pass`)

**Writes** (via `pipeline_bridge.confirm_anchors`, on Re-verify / Confirm):
- `annotated_blocks.json`, `comparison.json` — re-classified + re-verified against
  the user's chosen R/E/NOI rows (no AI re-call — reuses the saved structure map + signals)

**DB:** `Upload.current_step = 'noi_verification'` on Confirm & Continue

**Next:** `noi_verification`

## Behaviour
- Shows the anchor status + explanation, the passing R − E = NOI triples, and 3 row
  selectors (revenue / expense / NOI) pre-filled with the current pick.
- **Re-verify** re-runs `R − E = NOI` server-side against the chosen rows and shows
  green/red. **Confirm & Continue** locks them and moves to NOI verification.
- Live (per-keystroke) re-verify is a future JS enhancement; v1 re-verifies on submit.
