# upload page

**URL:** `/t12/`

**Reads:** nothing (entry point)

**Writes** (via `pipeline_bridge.run_detection`):
- `block_detection.json`
- `annotated_blocks.json`
- `actual_noi.json`
- `computed_noi.json`
- `comparison.json`

**DB:** creates `Upload` row with:
- `status='draft'`
- `current_step='upload'` → flipped to `'noi_verification'` after detection completes
- `file_name`, `property_name`, `file` (FileField → MEDIA_ROOT in dev, S3 in prod)

**Next:** redirects to `noi_verify` (`/t12/<upload_id>/noi/`)

**On pipeline error:** deletes the `Upload` row (cascade-removes the file) and re-renders the form with the error message.
