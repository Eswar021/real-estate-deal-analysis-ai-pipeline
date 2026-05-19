# Mapping Rulebook — Claude Instructions

Real estate T12 financial statement mapping pipeline for Oakdale Capital.
Reads raw Excel T12 files, maps every line item to a canonical category,
and verifies the computed NOI matches the vendor's reported NOI.

---

## How to Run

```bash
# Build rulebook (run once when new reviewed .xlsm files arrive)
python src/build_rulebook/run.py

# Full pipeline (manifest + detection + mapping)
python src/pipeline/run_pipeline.py --stages 0,1,2

# Just detection + mapping (reuses current_manifest.json from last Stage 0)
python src/pipeline/run_pipeline.py --stages 1,2

# Limit AI calls per file while testing
python src/pipeline/run_pipeline.py --stages 1,2 --ai-limit 5

# Individual stages
python src/pipeline/0_manifest/runner.py
python src/pipeline/1_detection/run_stage.py
python src/pipeline/2_mapping/run_stage.py

# Utils (export to Excel for review)
python src/pipeline/utils/auto_mapped_to_excel.py
python src/pipeline/utils/ai_mapped_to_excel.py
python src/pipeline/utils/convert_rulebook_to_excel.py
```

---

## Architecture

```
src/
    build_rulebook/           <- one-time tool: builds db/rulebooks/ from .xlsm reviews
        run.py                <- entry point: python src/build_rulebook/run.py
        build_rulebook.py     <- merges support artifacts -> db/rulebooks/mapping_rulebook_<ts>.json
        build_client_review_rules.py
        extract_reviewed_row_history.py
        build_historical_rule_support.py
    config/
        paths.py              <- all paths/dirs, single source of truth
        rulebook_runtime.py   <- build_rulebook script list + output path
        rulebook_utils.py     <- load/validate/flatten rulebook helpers
        agent_llm_config.py   <- model/provider selection per agent
    llm/
        llm_client.py         <- LLM client wrapper (OpenAI / Gemini / LM Studio)
    pipeline/
        0_manifest/           <- Stage 0: writes current_manifest.json + dated run_manifest.json
        1_detection/          <- Stage 1: detect_blocks -> annotate_totals -> compute_noi -> compare_noi
        2_mapping/            <- Stage 2: map_blocks -> find_mapping (AI fallback)
        utils/                <- export scripts, not part of main pipeline flow
        run_pipeline.py       <- master stage runner
    analysis/                 <- diagnostic notebooks, read-only

data/input_T12_docs/      <- raw .xlsx files (read-only)
db/rulebooks/             <- versioned rulebook snapshots (written by src/build_rulebook/)
output_docs/              <- all run outputs
    current_manifest.json <- always-latest pointer (overwritten each Stage 0 run)
    <timestamp>/          <- per-run output dir (e.g. 2026_05_18_1430/)
        run_manifest.json <- frozen snapshot for this run
        1_detection/
            block_detection/
            annotated_blocks/
            noi_verification/
        2_mapping/
            auto_mapped/
            ai_mapped/
```

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
- **Don't hardcode paths** — always use `config/paths.py`.
- **Don't scatter model selection** — always use `config/agent_llm_config.py`.
- **db/ is read-only for the pipeline.** `src/build_rulebook/` writes to `db/rulebooks/`.
- **Stage 1 only touches raw .xlsx in detect_blocks.** Downstream stages work from JSON only.

---

## What Not To Do

- Import from `archive/` or old analysis notebooks
- Reintroduce multiple active rulebook versions into the runtime path
- Make pipeline stages write to `db/` (only `src/build_rulebook/` does)
- Make downstream stages reopen raw Excel files
- Add `except: pass` or silent error swallowing
- Add hidden keyword heuristics in Stage 1 without being asked
- Change stage folder numbering (0, 1, 2) — the numbers are how this is discussed
- Add backwards-compatibility shims for removed code — just delete it cleanly
- Hardcode paths — stages 1 and 2 must read all paths from the manifest
