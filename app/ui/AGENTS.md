# Django UI — Codex Instructions

This file is for work under `app/ui/`.

The full architecture, page contract convention, storage abstraction,
and rules are in `app/ui/CLAUDE.md`. Read that file before planning or
implementing changes in the UI. The content applies equally to Codex,
Claude Code, and any other AI assistant.

Key invariants (full detail in CLAUDE.md):

- Pages under `t12_mapping/pages/<page>/` are self-contained and **never import each other**.
- Cross-page state lives in `storage/<upload_id>/pipeline/<file>.json`, accessed via `shared.storage`.
- The `Upload` model (`t12_mapping/models.py`) is the source of truth for "which uploads exist".
- Every page folder has a `README.md` declaring its `URL / Reads / Writes / DB / Next` contract.
- Templates live inside the page folder (`pages/<name>/templates/<name>/<file>.html`) and are auto-discovered by `config/settings.py`.
- `default_storage` indirection means swapping to S3 in prod is a settings change, not a code change.
