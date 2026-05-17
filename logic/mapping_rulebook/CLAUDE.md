# Mapping Rulebook — Claude Instructions

Real estate T12 financial statement mapping pipeline for Oakdale Capital.
Reads raw Excel T12 files, maps every line item to a canonical category,
and verifies the computed NOI matches the vendor's reported NOI.

---

## How to Run

```bash
# Full pipeline
python run_pipeline.py --stages 0,1,2

# Just mapping + NOI verification (most common)
python run_pipeline.py --stages 1,2

# Limit AI calls per file while testing
python run_pipeline.py --stages 1,2 --ai-limit 5

# Individual stages
python pipeline/0_build_rulebook/run_stage.py
python pipeline/1_mapping/run_stage.py
python pipeline/2_noi_verification/run_stage.py

# Utils (export to Excel for review)
python pipeline/utils/auto_mapped_to_excel.py
python pipeline/utils/ai_mapped_to_excel.py
python pipeline/utils/convert_rulebook_to_excel.py
```

---

## Architecture

```
config/
    paths.py              ← all paths/dirs, single source of truth
    rulebook_runtime.py   ← active rulebook path + Stage 0 builder chain
    rulebook_utils.py     ← load/validate/flatten rulebook helpers
    agent_llm_config.py   ← model/provider selection per agent

pipeline/
    0_build_rulebook/     ← builds mapping_rule_book.json from client-reviewed data
    1_mapping/            ← detect_blocks → map_blocks → find_mapping (AI fallback)
    2_noi_verification/   ← compute_noi → compare_noi
    utils/                ← export scripts, not part of main pipeline flow

data/input_T12_docs/      ← raw .xlsx files (read-only)
db/                       ← read-only snapshots, never written to by pipeline
output_docs/{date}/       ← all run outputs, date-stamped
```

---

## Stage Contracts

**Stage 1 JSON row fields (keep stable):**
- `row`, `type`, `description`, `section_context`, `section_path`, `values`
- `statement_side` — `"revenue"` / `"expense"` / `"capex"`, set by detect_blocks
- `mapping`, `not_found`, `mapping_source`
- `ai_suggested_mapping`, `ai_confidence`, `ai_reasoning` — added by find_mapping

**Rulebook shape:**
```json
{ "certain": {}, "contextual": {}, "no_conflict": {}, "unresolved": {} }
```

Lookup order in map_blocks: certain → contextual → no_conflict → unresolved (→ AI)

---

## Block Detection Logic (detect_blocks.py)

Three file formats: `code_in_a_desc_in_b`, `embedded_code_in_a`, `no_code`

Row types: `data` / `subtotal` / `header` / `empty`

`statement_side` is assigned structurally via a two-flag state machine:
- Flip `income_phase_complete` when a subtotal matches grand income total markers
  (`total income`, `total revenue`, `effective gross income`, `total operating revenues`)
- Flip `capex_phase_complete` when a subtotal contains `net operating income`
  (only checked after income flip — guards against summary rows at top of some files)
- Data rows before income flip → `revenue`, after → `expense`, after NOI flip → `capex`
- Capex rows are excluded from all mapping and NOI computation

---

## Coding Rules

- **Small functions, direct paths.** No deep abstraction chains.
- **Fail hard.** Missing file or broken schema assumption → stop, don't silently continue.
- **No premature abstractions.** Three clear lines beat a clever helper.
- **No comments explaining what the code does** — only add one when the WHY is non-obvious.
- **No silent fallbacks or best-effort guesses** in core mapping logic unless explicitly asked.
- **Don't add error handling for things that can't happen.** Trust internal guarantees.
- **Don't hardcode paths** — always use `config/paths.py`.
- **Don't scatter model selection** — always use `config/agent_llm_config.py`.
- **db/ is read-only.** Stage 0 writes to output_docs/ only.
- **Stage 1 only touches raw .xlsx in detect_blocks.** Downstream stages work from JSON only.

---

## What Not To Do

- Import from `archive/` or old analysis notebooks
- Reintroduce multiple active rulebook versions into the runtime path
- Write Stage 0 outputs into `db/`
- Make downstream stages reopen raw Excel files
- Add `except: pass` or silent error swallowing
- Add hidden keyword heuristics in Stage 1 mapping without being asked
- Change stage folder numbering (0, 1, 2) — the numbers are how this is discussed
- Add backwards-compatibility shims for removed code — just delete it cleanly
