# upload page

**URL:** `/t12/`  (also the "Continue anyway" override POST target)

**Reads:** nothing (entry point)

**Pre-check (Stage 0) is a warning, not a wall.** `pipeline_bridge.run_preflight` still flags
rent rolls / Model-T12 / non-T12 files, but a rejection no longer deletes the upload — the file
is kept and the page shows the reason + a **"Continue anyway"** button (a POST with
`bypass_upload_id`). Clicking it skips the pre-check and runs Stage 1. (The check can't recognise
every vendor's wording — e.g. Pratt, a valid T12 whose expense total omits the word "Total"; and
a genuinely-wrong file just hits a wall at the anchor gate, so the override is safe.)

**Writes** (via `pipeline_bridge.run_detection` — **STAGE 1 only**, up to the R − E = NOI
anchor lock; classification is deferred to the anchor gate):
- `anchor_lock.json` — status (AUTO / DERIVED / GATE / NONE), candidates, passing triples, locked anchors
- `parse_state.json` — format + final_map + anchor_rows (the light Stage-1 rows for the gate;
  Stage 2 re-extracts the full signal vector from cell_grid — no AI re-call)
- `cell_grid.json`

It does **not** write `annotated_blocks.json` / `comparison.json` / `actual_noi.json` — those
are Stage-2 outputs the anchor gate writes on Confirm.

**DB:** creates `Upload` row with:
- `status='draft'`
- `current_step='upload'` (stays until the anchor gate bumps it to `'noi_verification'` on Confirm)
- `file_name`, `property_name`, `file` (FileField → MEDIA_ROOT in dev, S3 in prod)

**Next:** always redirects to `anchor_gate` (`/t12/<upload_id>/anchors/`). Every upload stops
there — classification (Stage 2) runs only after the anchors are confirmed. A clean AUTO lock
arrives pre-filled and reconciling (a one-click confirm); an ambiguous lock needs a real choice.

**On pipeline error:** deletes the `Upload` row (cascade-removes the file) and re-renders the form with the error message.
