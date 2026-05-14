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
