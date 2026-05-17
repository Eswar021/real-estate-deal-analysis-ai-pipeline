# Mapping Rulebook — Codex Instructions

This file is for work under `logic/mapping_rulebook/`.
Follow everything here before generating code for this pipeline.

## Read First

Before planning or changing any stage:

1. Read `docs/README.md`
2. Read `docs/WORKING_STYLE.md`

If you are changing stage contracts, rulebook structure, runner behavior, or
output locations, also read:

3. `docs/CONTEXT.md`
4. `docs/DECISIONS.md`

If you are changing the actual parsing or mapping algorithm, also read:

5. `docs/LOGIC.md`

If you need older chat context, use these as reference only:

- `archive/references/codex_chats.txt`
- `archive/mapping_rulebook_docs/`

Do not treat archived notes as the active source of truth.

---

## Project Architecture

We are maintaining a clean, numbered T12 mapping pipeline under
`logic/mapping_rulebook/`.

```text
logic/mapping_rulebook/
├── config/
│   ├── paths.py
│   ├── rulebook_runtime.py
│   ├── rulebook_utils.py
│   └── agent_llm_config.py
├── pipeline/
│   ├── 0_build_rulebook/
│   ├── 1_mapping/
│   ├── 2_noi_verification/
│   └── utils/
├── llm/
├── data/
├── db/             ← read-only snapshots only
├── output_docs/    ← all dated run outputs
├── docs/
└── archive/        ← reference only, never part of active flow
```

The active pipeline is:

```text
Stage 0: build rulebook artifacts
Stage 1: detect rows -> auto-map -> AI fallback
Stage 2: compute NOI -> compare NOI
```

The older experiments and archived logic are reference only.
Do not wire active code to `archive/`, old notebooks, or deprecated builder flows.

---

## Active Pipeline Flow

### Stage 0 — Rulebook Build

The current build chain is:

1. `build_client_review_rules.py`
2. `extract_reviewed_row_history.py`
3. `build_historical_rule_support.py`
4. `build_rulebook.py`

The current runtime rulebook output is:

```text
output_docs/{date}/0_build_rulebook/mapping_rulebook/mapping_rule_book.json
```

The current rulebook shape is:

```python
{
    "certain": {...},
    "contextual": {...},
    "no_conflict": {...},
    "unresolved": {...},
}
```

Lookup order in Stage 1 is:

1. `certain`
2. `contextual`
3. `no_conflict`
4. `unresolved` -> AI

### Stage 1 — Mapping

The Stage 1 flow is:

1. `detect_blocks.py`
2. `map_blocks.py`
3. `find_mapping.py`

Important:

- `detect_blocks.py` is the only Stage 1 script that should read raw `.xlsx`
  files from `data/input_T12_docs/`
- after block detection, downstream steps must work from JSON artifacts only
- `map_blocks.py` must not reopen the raw Excel files
- `find_mapping.py` must read `auto_mapped/*.json`, not the raw Excel files

### Stage 2 — NOI Verification

The Stage 2 flow is:

1. `compute_noi.py`
2. `compare_noi.py`

Keep these as simple executable scripts. Do not over-framework this layer.

---

## Golden Rules

### One Current Rulebook Only

- The active runtime path uses one current rulebook only
- do not reintroduce live `v1 / v2 / v3` switching into the active pipeline
- `config/rulebook_runtime.py` should point to one builder chain and one runtime artifact

Older rulebook experiments can remain as references, but they must not control
the active runtime path.

### `db/` Is Read-Only

- Stage 0 writes only to `output_docs/`
- `db/` is a read-only snapshot area if we want to bless a build later
- do not make Stage 0 write directly into `db/`

### No Silent Guessing In Core Logic

- If the current rulebook can map a row, map it
- if exact learned section support can resolve a contextual rule, use it
- if it cannot, leave the row unresolved and let the AI stage handle it

Do not add hidden keyword fallbacks, broad fuzzy logic, or best-effort guesses
inside the core Stage 1 mapping path unless explicitly asked.

### Keep Contracts Stable

- preserve the existing Stage 1 JSON contract
- adding non-breaking metadata is okay if it materially helps downstream AI or auditability
- do not casually rename or remove keys used by later stages

### Numbered Stages Stay

Keep these folders and stage numbers:

- `0_build_rulebook`
- `1_mapping`
- `2_noi_verification`

The numbers are part of how this project is understood and discussed.

---

## Coding Philosophy

### Keep It Visible

- Small functions
- One logical unit per function
- Direct execution paths
- No deep abstraction chains
- `if __name__ == "__main__"` harnesses are acceptable while a stage is evolving

### Fail Hard

Do not silently continue when assumptions break:

- missing expected input file -> stop
- missing config / path assumption -> stop
- broken schema assumption -> stop
- unexpected shape in reviewed history or rulebook -> stop

Accounting-oriented pipelines should fail loudly during development.

### No Premature Frameworks

- Prefer thin runners over architectural rewrites
- Prefer explicit code over generic dispatch
- Three simple lines are better than a clever abstraction that hides the flow

---

## Config Rules

Use these files as the only active config sources:

- `config/paths.py` -> all paths and output locations
- `config/rulebook_runtime.py` -> current runtime rulebook path and Stage 0 builder chain
- `config/agent_llm_config.py` -> agent -> provider/model selection

Do not hardcode file-system paths in stage logic.
Do not scatter model selection across multiple files.

---

## Stage 1 Output Contract

The important Stage 1 JSON shape should stay stable.

Top-level fields should remain:

- `file`
- `file_path`
- `format`
- `data_start_row`
- `column_headers`
- `summary`
- `rows`

For row entries, the important fields are:

- `row`
- `type`
- `description`
- `section_context`
- `section_path`
- `values` for data/subtotal rows
- `mapping`
- `not_found`
- `mapping_source`

Non-breaking metadata currently used by downstream AI/audit flow includes:

- `inferred_statement_side`
- `statement_side_source`
- `client_review_note`
- `unresolved_reason_type`
- `historical_candidate_mappings`
- `historical_statement_sides`
- `historical_section_paths`

If you add more metadata, keep it additive and documented.

---

## AI Mapping Rules

`find_mapping.py` is the AI fallback stage.

Rules:

- It runs only on rows where `not_found` is `true`
- It must choose from the current canonical categories only
- It must use the current runtime rulebook, not any archived rulebook snapshot
- It should consume Stage 1 JSON context, not re-parse the source Excel

Preserve prompt/response logging under:

```text
output_docs/{date}/1_mapping/ai_mapping_logs/
```

Full prompts and model responses are useful here. Do not strip them down to the
point that audits become difficult.

---

## Script Docstring Standard

Every stage runner or major executable script should have a module docstring that states:

- what it does
- what it reads
- what it writes
- whether it calls an LLM
- the internal execution order if helpful
- how to run it

Keep docstrings factual and short. They should help a future session understand
the script without opening three more files.

---

## Documentation Rules

When active behavior changes, update the active docs:

- `docs/README.md` for overview and run flow
- `docs/CONTEXT.md` for paths, contracts, and script inventory
- `docs/LOGIC.md` for algorithm behavior
- `docs/DECISIONS.md` for design choices and rationale
- `docs/audits/` for dated system-state snapshots when the overall system state changes materially

The docs are part of the runtime memory for this project. Keep them in sync.

---

## What Not To Do

- Do not import from `archive/`
- Do not import from old notebooks in `analysis/`
- Do not reintroduce multiple active rulebook versions into the runtime path
- Do not write Stage 0 outputs into `db/`
- Do not make downstream mapping stages reopen raw Excel files
- Do not add silent `except: pass`
- Do not add hidden keyword heuristics in Stage 1 unless explicitly requested
- Do not create new side-output files unless they are part of the documented stage contract
- Do not change stage numbering or folder names casually
