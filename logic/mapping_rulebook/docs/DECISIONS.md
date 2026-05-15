# Mapping Rulebook Decisions

Short decision log for active structural choices in `logic/mapping_rulebook/`.

---

## 2026-05-15 — Documentation Paths

Decision:

- keep active technical documentation under `logic/mapping_rulebook/docs/`
- keep broader project meeting materials and client-shared artifacts under `master_docs/`

Why:

- technical docs should live next to the code they describe
- large meeting and client files should stay separated from the code-facing docs
- the split makes it clearer which docs are operational versus archival

---

## 2026-05-15 — Coding Style

Decision:

- keep core stage logic simple
- prefer single-item or single-file functions
- use `__main__` blocks as temporary manual harnesses during development
- build dedicated runners later instead of prematurely hiding the workflow

Why:

- this makes the pipeline easier to inspect while the logic is still evolving
- failures become easier to localize
- the code stays understandable without over-abstracting too early

---

## 2026-05-15 — Fail Hard Inside Stages

Decision:

- do not add broad silent fallbacks inside the core mapping stages

Why:

- this pipeline affects accounting outputs and NOI verification
- silent fallback behavior can hide real mapping mistakes
- obvious failure is preferred during development and audit-oriented iteration

---

## 2026-05-15 — Numbered Pipeline Folders Stay

Decision:

- preserve numbered stage folders such as `0_build_rulebook`, `1_mapping`, and `2_noi_verification`

Why:

- the numbers immediately communicate execution order
- they make docs, audits, and runner planning easier to follow
- they reduce ambiguity when discussing "what comes before what"

---

## 2026-05-15 — Manual Rulebook A/B Testing Is Allowed

Decision:

- during development, rulebook A/B testing should be controlled from one central config file: `config/rulebook_runtime.py`

Why:

- the current need is to compare mapping behavior and downstream NOI verification between rulebook versions
- one central switch is simpler and safer than editing multiple downstream files

Follow-up:

- when a dedicated runner is introduced, rulebook selection should become an explicit runner parameter instead of a config-only workflow

---

## 2026-05-15 — Agent Model Selection Is Centralized

Decision:

- keep agent → provider/model selection in `config/agent_llm_config.py`

Why:

- the mapping agent should not hardcode its model inside stage logic
- future agents can be added without rewriting `llm_client.py`
- model changes become a config update instead of a code-edit sweep

---

## 2026-05-15 — Stage 2 Has Two Executable Scripts Today

Decision:

- keep Stage 2 as two executable scripts for now:
  - `compute_noi.py`
  - `compare_noi.py`
- keep the logical "extract actual NOI" substep inside `compute_noi.py`

Why:

- this matches the current development style
- the substeps are closely related and easier to inspect together right now
- a separate orchestration runner can split or sequence them later if needed

---

## 2026-05-15 — Thin Runners Over Heavy Refactors

Decision:

- keep the existing single-item stage modules as the source of truth for logic
- add thin stage runners for `0_build_rulebook`, `1_mapping`, and `2_noi_verification`
- add one master runner that sequences the stage runners instead of moving logic into a new framework

Why:

- this preserves the current inspectable, fail-hard module style
- orchestration becomes reusable without hiding the raw stage code
- later runner changes can happen without rewriting the core business logic

---

## 2026-05-15 — Stage Selection Must Be Explicit

Decision:

- the master runner must not assume default stages
- every pipeline run must pass either `--stages` or both `--from-stage` and `--to-stage`

Why:

- explicit run scope makes testing safer
- it removes ambiguity about whether a run is partial or end-to-end
- this matches the repo's preference for visible, intentional execution

---

## 2026-05-15 — Stage 0 Writes To Output Only

Decision:

- Stage 0 builders write rulebooks and category classification only under `output_docs/`
- `db/` stays read-only from the pipeline's point of view

Why:

- build artifacts should stay versioned by run date
- runtime testing should use the current build outputs directly
- reference snapshots in `db/` should not be overwritten by routine pipeline runs

---

## 2026-05-15 — Client Review And Historical XLSM Extraction Stay Separate

Decision:

- keep the client-reviewed conflict workbook build separate from the 19 reviewed `.xlsm` history extraction
- first build `certain / contextual / unresolved` from the reviewed client workbook
- separately extract historical row context from the `.xlsm` files before building `no_conflict`

Why:

- this avoids mixing two different sources of truth too early
- client-reviewed decisions should stay explicit and inspectable
- the later `no_conflict` builder can work from a clean historical extraction artifact instead of reparsing spreadsheets every time

---

## 2026-05-15 — V3 Rulebook Is Built Separately Before Runtime Integration

Decision:

- build the new sectioned v3 rulebook as a separate Stage 0 artifact first
- do not switch the active runtime profile to v3 until `map_blocks.py` and later mapping logic are updated to read the new structure

Why:

- the current runtime still expects the older flat `category -> [descriptions]` rulebook shape
- forcing v3 into the runtime too early would break the existing mapping stage
- keeping v3 separate lets us validate the new structure before changing downstream consumers
