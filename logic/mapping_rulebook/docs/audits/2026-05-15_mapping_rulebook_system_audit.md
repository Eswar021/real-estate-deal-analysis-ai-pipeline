# 2026-05-15 Mapping Rulebook System Audit

## Scope

This audit records the current active state of `logic/mapping_rulebook/` after the docs-folder refactor and before a dedicated pipeline runner has been introduced.

It focuses on:

- active folder and documentation paths
- the real script inventory versus the older docs
- intentional development patterns that should not be mistaken for accidental cleanup debt
- current drifts that are acceptable for now versus changes that were corrected

---

## Executive Summary

- The active code-facing docs now live under `logic/mapping_rulebook/docs/`.
- The broader project docs at repo root now live under `master_docs/`.
- `config/paths.py` already points `DOCS_DIR` at `PROJECT_ROOT / "docs"` and did not need a logic change.
- The root README had stale references to `mapping_rulebook_docs/` and `Docs/`; those were corrected.
- The active mapping docs had an outdated Stage 2 description that referenced a non-existent `extract_actual_noi.py` script. This was corrected to match the real implementation: `compute_noi.py` handles both logical substeps.
- The repo intentionally uses simple stage modules plus temporary `__main__` harnesses. That pattern is now documented as a deliberate working style, not a bug.
- Runtime rulebook selection is now centralized in `config/rulebook_runtime.py` so v1 versus v2 testing does not require edits across multiple stage files.
- Agent → model/provider selection is now centralized in `config/agent_llm_config.py` and consumed through `llm/llm_client.py`.

---

## 1. Active Documentation Layout

### Current intended structure

- `logic/mapping_rulebook/docs/README.md`
- `logic/mapping_rulebook/docs/CONTEXT.md`
- `logic/mapping_rulebook/docs/LOGIC.md`
- `logic/mapping_rulebook/docs/WORKING_STYLE.md`
- `logic/mapping_rulebook/docs/DECISIONS.md`
- `logic/mapping_rulebook/docs/audits/`

### Non-code project materials

- `master_docs/`

This separation is healthy:

- `logic/mapping_rulebook/docs/` is for active technical understanding of the pipeline
- `master_docs/` is for recordings, client documents, and larger project references

---

## 2. Stage Inventory Versus Older Docs

### Actual executable Stage 2 scripts today

- `pipeline/2_noi_verification/compute_noi.py`
- `pipeline/2_noi_verification/compare_noi.py`

### Important clarification

The pipeline still has a logical Stage 2a and 2b:

- extract vendor-reported NOI
- compute our NOI from mapped rows

But both logical substeps currently live inside `compute_noi.py`.

Older docs described a separate `extract_actual_noi.py` file. That was documentation drift, not the current architecture.

---

## 3. Working Style Audit

### Intentional patterns

The following patterns are intentional and should be preserved unless the team explicitly decides otherwise:

- simple stage logic over premature abstraction
- reusable functions focused on one logical unit of work
- `if __name__ == "__main__"` blocks used as temporary manual harnesses
- fail-hard behavior inside core stage modules
- runner/orchestrator work deferred until stage logic is stable

This is not "unfinished by accident." It is the current development method for this repo.

### Why it works for this project

- accounting-oriented transformations are easier to audit when the code path is direct
- hard failures surface bad assumptions earlier
- manual harnesses make it faster to inspect intermediate behavior during pipeline design

---

## 4. Rulebook Version Testing

### Target documented architecture

The docs describe `db/mapping_rule_book_v2.json` as the intended active rulebook.

### Current development reality

Manual v1 versus v2 comparison is still being done during development to verify downstream NOI behavior.

That comparison is now meant to be controlled from:

- `config/rulebook_runtime.py`

### Important operational note

The central config now keeps the selected rulebook aligned across all affected stages, especially:

- `pipeline/1_mapping/map_blocks.py`
- `pipeline/1_mapping/find_mapping.py`
- `pipeline/0_build_rulebook/category_config.py`
- `pipeline/utils/convert_rulebook_to_excel.py`

---

## 5. LLM Configuration State

### Current code reality

LLM provider selection is owned by `config/agent_llm_config.py` and resolved by `llm/llm_client.py`.

Supported providers in the current code:

- OpenAI
- Gemini
- LM Studio

### Corrected doc drift

Some active docs previously implied that the AI fallback was always Gemini. That is no longer accurate as a general statement, so the docs were updated to describe the provider as configurable through `llm_client.py`.

---

## 6. Remaining Intentional Drifts

These are acceptable for now and should not be "cleaned up" automatically:

- manual `__main__` harnesses instead of a dedicated runner
- per-stage scripts that can be run independently for inspection

These are future improvements, not current correctness bugs:

- introduce dedicated runners for stage batches
- parameterize rulebook choice in runners instead of comment/uncomment imports
- maintain additional dated audits as the system evolves

---

## 7. Recommendation

Near-term:

1. Keep the current simple module structure.
2. Keep using dated audits under `docs/audits/`.
3. Update docs whenever a stage contract changes.

Later:

1. Add a dedicated runner layer once the stage contracts stop moving frequently.
2. Move rulebook selection to runner parameters or config once A/B testing settles down.
3. Keep the active docs lean: overview, context, logic, working style, decisions, and dated audits are enough for now.
