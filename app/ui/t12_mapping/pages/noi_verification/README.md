# noi_verification page — Classification Review (Stage 2, 2nd hard stop)

**URL:** `/t12/<upload_id>/noi/`

The second hard stop. Every file lands here after the anchor gate is confirmed, pass or
fail. Shows the NOI verification on top and **every classified row bucketed by section**
(revenue / expense / capex), each with its 7-class label, total, and confidence — anchor
rows and low-confidence rows flagged. The user can **correct any row's class** here and
re-verify.

**Reads:** the **run-state** via `bridge.get_state(id, with_grid=False)`. The page-local
presenter (`helpers.build_view`) turns the run-state's `classification` slice + confirmed
anchors into the review view (confirmed anchors, per-month NOI, every classified row with
class / section / values / confidence / low_confidence / source). No cell_grid needed —
`column_headers` were computed at classify time.

**Writes:** the run-state.
- **Re-verify** → `run_step(id, "stage2_reverify", class_edits={row: CLASS})` → rewrites
  `classification.classified` / `.noi` / `.low_confidence_rows`.
- **Save & Continue** → `run_step(id, "stage3_mapping")` → writes `state.mapping`, then
  redirects to `data_review`.

**DB:** `Upload.current_step = 'data_review'` on Save & Continue.

**Next:** `data_review`.

## Pass/fail (helpers.ui_pass)
Green only when **NOI reconciles AND** the revenue and expense totals both match — two green
lights, since a net NOI check alone can hide compensating misclassifications. The totals come
from the run-state's `classification.noi` (which already sums an expense split-pair and
tolerates the vendor's sign convention).

## Behaviour
- **Class dropdown** on every row except the locked anchors (R / E / NOI + any expense split
  rows) — those are the target NOI is checked *against*, so the page doesn't offer to move them.
  `stage2_reverify` refuses them too; the page isn't the enforcement point.
- **Re-verify** applies the changed dropdowns and re-runs the NOI check — nothing else. It does
  **not** re-classify (recomputing the scores would silently undo the edit — exactly what the
  old Recompute did) and does **not** call the AI (it had its turn during `stage2_classify`;
  re-running it would fight the user, one LLM call per edit). Changing a dropdown disables
  **Save & Continue** until Re-verify runs, so an unapplied edit can never be what gets mapped.
- **Source badge** — each row carries `source` ∈ `auto` | `ai` | `manual`. `AI` badge = the
  diagnosis reclassified it (tooltip = its reason); `edited` = the user did. Display only: no
  behaviour hangs off the tag, and no edit is ever locked (nothing re-runs to overwrite it).
- **Save & Continue** runs mapping and moves on.
- Low-confidence rows (small top-two class margin, value-bearing) are highlighted for review.
