# noi_verification page — Classification Review (Stage 2, 2nd hard stop)

**URL:** `/t12/<upload_id>/noi/`

The second hard stop. Every file lands here after the anchor gate is confirmed, pass or
fail. Shows the NOI verification on top and **every classified row bucketed by section**
(revenue / expense / capex), each with its 7-class label, total, and confidence — anchor
rows and low-confidence rows flagged.

**Reads:** the **run-state** via `bridge.get_state(id, with_grid=False)`. The page-local
presenter (`helpers.build_view`) turns the run-state's `classification` slice + confirmed
anchors into the review view (confirmed anchors, per-month NOI, every classified row with
class / section / values / confidence / low_confidence). No cell_grid needed — `column_headers`
were computed at classify time.

**Writes** (on **Recompute**, via `run_step("classify", run_feedback=False)` → deterministic,
no AI): the run-state. On **Save & Continue** it also runs Stage 3 mapping (`run_mapping`,
which builds its input from the run-state and writes `state.mapping`).

**On Save & Continue:** runs the mapping stage (`run_mapping`, reads `annotated_blocks.json`)
then redirects to `data_review`.

**DB:** `Upload.current_step = 'data_review'` on Save & Continue.

**Next:** `data_review`.

## Pass/fail (helpers.ui_pass)
Green only when **NOI reconciles AND** the revenue and expense totals both match — two green
lights, since a net NOI check alone can hide compensating misclassifications. The totals come
straight from `classification.json` (which already sums an expense split-pair and tolerates
the vendor's sign convention).

## Behaviour
- **Recompute** re-runs Stage 2 on adjusted R / E / NOI anchors **deterministically** (no AI
  diagnosis — that ran once on the gate Confirm).
- **Save & Continue** runs mapping and moves on.
- Low-confidence rows (small top-two class margin, value-bearing) are highlighted for review.
