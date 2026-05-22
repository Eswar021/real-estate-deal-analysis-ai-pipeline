# Mapping Rulebook — Claude Instructions

Real estate T12 financial statement mapping pipeline for Oakdale Capital.
Reads raw Excel T12 files, maps every line item to a canonical category,
and verifies the computed NOI matches the vendor's reported NOI.

Packaged as a proper Python package (`t12_pipeline`) — install in editable
mode once with `pip install -e ./app/t12_pipeline`. All entry points are
`python -m`, no `sys.path` manipulation anywhere.

---

## How to Run

```bash
# One-time setup (editable install — picks up source changes automatically)
pip install -e ./app/t12_pipeline

# Build rulebook (run once when new reviewed .xlsm files arrive)
python -m t12_pipeline.build_rulebook.run

# Full pipeline (manifest + detection + mapping)
python -m t12_pipeline.pipeline.run_pipeline --stages 0,1,2

# Just detection + mapping (reuses current_manifest.json from last Stage 0)
python -m t12_pipeline.pipeline.run_pipeline --stages 1,2

# Limit AI calls per file while testing
python -m t12_pipeline.pipeline.run_pipeline --stages 1,2 --ai-limit 5

# Individual stages
python -m t12_pipeline.pipeline.manifest.runner
python -m t12_pipeline.pipeline.detection.run_stage
python -m t12_pipeline.pipeline.mapping.run_stage

# Utils (export to Excel for review)
python -m t12_pipeline.pipeline.utils.auto_mapped_to_excel
python -m t12_pipeline.pipeline.utils.ai_mapped_to_excel
python -m t12_pipeline.pipeline.utils.convert_rulebook_to_excel
```

---

## Architecture

```
app/t12_pipeline/
├── pyproject.toml                   <- declares the t12_pipeline package
└── src/
    ├── t12_pipeline/                <- the installable package
    │   ├── build_rulebook/          <- one-time tool: builds db/rulebooks/ from .xlsm reviews
    │   │   ├── run.py               <- entry: python -m t12_pipeline.build_rulebook.run
    │   │   ├── build_rulebook.py
    │   │   ├── build_client_review_rules.py
    │   │   ├── extract_reviewed_row_history.py
    │   │   └── build_historical_rule_support.py
    │   ├── config/
    │   │   ├── paths.py             <- all paths/dirs, single source of truth
    │   │   ├── rulebook_runtime.py  <- build_rulebook module list + output path
    │   │   ├── rulebook_utils.py    <- load/validate/flatten rulebook helpers
    │   │   └── agent_llm_config.py  <- model/provider selection per agent
    │   ├── llm/
    │   │   └── llm_client.py        <- LLM client wrapper (OpenAI / Gemini / LM Studio)
    │   └── pipeline/
    │       ├── manifest/            <- Stage 0: writes current_manifest.json + dated run_manifest.json
    │       ├── detection/           <- Stage 1: detect_blocks -> annotate_totals -> compute_noi -> compare_noi
    │       │   └── corrections.py   <- UI correction layer (apply_corrections + recompute_noi)
    │       ├── mapping/             <- Stage 2: map_blocks -> find_mapping (AI fallback)
    │       ├── utils/               <- export scripts, not part of main pipeline flow
    │       ├── runner_utils.py      <- run_python_module(): subprocess wrapper for `python -m`
    │       └── run_pipeline.py      <- master stage runner
    └── analysis/                    <- diagnostic notebooks, not part of the package

data/input_T12_docs/      <- raw .xlsx files (read-only)
db/rulebooks/             <- versioned rulebook snapshots (written by t12_pipeline.build_rulebook)
output_docs/              <- all run outputs
    current_manifest.json <- always-latest pointer (overwritten each Stage 0 run)
    <timestamp>/          <- per-run output dir (e.g. 2026_05_18_1430/)
        run_manifest.json <- frozen snapshot for this run
        1_detection/      <- folder kept numbered to preserve stage-N semantics in outputs
            block_detection/
            annotated_blocks/
            noi_verification/
        2_mapping/
            auto_mapped/
            ai_mapped/
```

Note: the **source folders** (`detection/`, `mapping/`, `manifest/`) dropped
their digit prefix so they're valid Python identifiers (Python module names
can't start with a digit). The **stage numbers** (0/1/2) still appear in
`run_pipeline.py`'s `STAGE_MODULES` dict, in `output_docs/<ts>/` subfolder
names, and in conversation ("Stage 0", "Stage 1", "Stage 2").

---

## Manifest-Driven Pipeline

`output_docs/current_manifest.json` is the single config source for stages 1 and 2.
It is written by Stage 0 (`0_manifest/runner.py`) and embeds:
- Full rulebook contents (`rulebook` key)
- All input file paths (`l1.input_files`)
- All Stage 1 output dirs (`l1.paths`: block_detection, annotated_blocks, actual_noi, computed_noi, noi_comparison)
- AI provider/model config (`l2.ai`)
- All Stage 2 output dirs (`l2.paths`: auto_mapped, ai_mapped, ai_mapping_logs)
- Run metadata (run_id, output_base, rulebook_source)

Stages 1 and 2 read everything from `MANIFEST_PATH` — they never recompute date-stamped paths.
This fixes the date-rollover bug where running stages the next day failed with FileNotFoundError.

Stage 2 reads its input from `l1.paths.annotated_blocks_dir` (Stage 1 output).

---

## Stage Contracts

**Detection output JSON row fields (keep stable):**
- `row`, `type`, `description`, `section_context`, `section_path`, `values`
- `statement_side` — `"revenue"` / `"expense"` / `"capex"`, set by detect_blocks
- `is_total_revenue`, `is_total_expense`, `is_noi` — boolean flags, set by annotate_totals

**Mapping output row fields (added by Stage 2):**
- `mapping`, `not_found`, `mapping_source`
- `ai_suggested_mapping`, `ai_confidence`, `ai_reasoning` — added by find_mapping

**Rulebook shape:**
```json
{ "certain": {}, "contextual": {}, "no_conflict": {}, "unresolved": {} }
```

Lookup order in map_blocks: certain -> contextual -> no_conflict -> unresolved (-> AI)

---

## Block Detection Logic

Three formats: `code_in_a_desc_in_b`, `embedded_code_in_a`, `no_code` — per-format classifiers in `1_detection/formats/`.
Row types: `data` / `subtotal` / `header` / `empty`.
`statement_side` via two-flag state machine: revenue → expense (at EGI subtotal) → capex (at NOI subtotal).
Subtotal rows get statement_side from state BEFORE the flip. Full decision trees: `docs/detection_logic/`.

---

## NOI Verification (Stage 1c + 1d)

Stage 1 computes and verifies NOI without mapping — uses `statement_side` directly.

`compute_noi.py` produces two files per T12:
- `actual_noi`: vendor's reported NOI from the `is_noi` subtotal row
- `computed_noi`: row-method sum (revenue rows - expense rows), plus `is_total_revenue` subtotal anchor

`compare_noi.py` runs two verification layers:
1. **NOI check**: row-method computed NOI vs vendor's actual NOI (within $1 or 0.1%)
2. **Revenue accuracy**: row-method revenue vs vendor's EGI (`is_total_revenue` subtotal)
3. **Expense accuracy**: implied expense (EGI - actual_noi) vs row-method expense sum

---

## Coding Rules

- **Small functions, direct paths.** No deep abstraction chains.
- **Fail hard.** Missing file or broken schema assumption -> stop, don't silently continue.
- **No premature abstractions.** Three clear lines beat a clever helper.
- **No comments explaining what the code does** — only add one when the WHY is non-obvious.
- **No silent fallbacks or best-effort guesses** in core mapping logic unless explicitly asked.
- **Don't add error handling for things that can't happen.** Trust internal guarantees.
- **Don't hardcode paths** — always use `t12_pipeline.config.paths`.
- **Don't scatter model selection** — always use `t12_pipeline.config.agent_llm_config`.
- **db/ is read-only for the pipeline.** `t12_pipeline.build_rulebook` writes to `db/rulebooks/`.
- **Stage 1 only touches raw .xlsx in detect_blocks.** Downstream stages work from JSON only.
- **No `sys.path` manipulation.** The package is installed via `pip install -e`; use real imports.

---

## What Not To Do

- Import from `archive/` or old analysis notebooks
- Reintroduce multiple active rulebook versions into the runtime path
- Make pipeline stages write to `db/` (only `t12_pipeline.build_rulebook` does)
- Make downstream stages reopen raw Excel files
- Add `except: pass` or silent error swallowing
- Add hidden keyword heuristics in Stage 1 without being asked
- Reintroduce digit-prefixed package directories (`0_manifest`, `1_detection`, `2_mapping`) — stage numbers stay in `STAGE_MODULES` and output folders, not in source dir names
- Add `sys.path.append(...)` blocks back into modules
- Add backwards-compatibility shims for removed code — just delete it cleanly
- Hardcode paths — stages 1 and 2 must read all paths from the manifest
