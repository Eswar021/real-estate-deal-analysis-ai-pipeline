# T12 Mapping Pipeline

Automated system that reads Trailing-12-Month (T12) financial Excel files from
multifamily property sellers, maps every line item to Oakdale Capital's canonical
chart-of-accounts categories, and verifies that the computed NOI matches the
vendor-reported NOI.

---

## What Problem It Solves

Each property seller submits T12 financials in their own format — different column
layouts, different account naming conventions, different file structures. Before
this system, every file had to be manually reviewed and mapped by hand.

This pipeline:
1. Automatically classifies every row in a raw T12 file (income line, expense line,
   subtotal, or section header).
2. Maps each line item to Oakdale's standard categories using a learned rulebook.
3. Falls back to an AI model for any line items not seen before.
4. Verifies that the total NOI computed from the mapped rows matches what the vendor
   reported — catching mapping errors before they reach the analysis stage.

---

## What It Produces

For each T12 file processed:

| Output | Description |
|---|---|
| `block_detection/*.json` | Every row classified as data / header / subtotal / empty |
| `auto_mapped/*.json` | DATA rows with rulebook mapping applied |
| `ai_mapped/*.json` | Unmapped rows filled in by AI; final file ready for analysis |
| `ai_mapped_to_excel/*.xlsx` | Styled Excel version of the final mapping for human review |
| `comparison/*.json` | Month-by-month NOI verification: PASS or FAIL with diff |

---

## Pipeline Overview

The pipeline has two phases: a one-time rulebook build, and per-file processing.

```
ONE-TIME SETUP (run when adding new source files or reviewing conflicts)
────────────────────────────────────────────────────────────────────────
Step 0a  build_client_review_rules
                                Parse the client-reviewed conflict workbook into:
                                certain / contextual / unresolved
                                → output_docs/0_build_rulebook/client_review_rules/

Support  extract_reviewed_row_history
                                Extract historical row context from the 19 reviewed
                                `.xlsm` files for later no_conflict / conflict work
                                → output_docs/0_build_rulebook/reviewed_row_history/

Support  build_historical_rule_support
                                Split the historical layer into:
                                no_conflict + historical_conflicts
                                → output_docs/0_build_rulebook/historical_rule_support/

Support  build_rulebook
                                Merge:
                                certain + contextual + no_conflict + unresolved
                                → output_docs/0_build_rulebook/mapping_rulebook/


PER FILE (run for every new T12 file received)
──────────────────────────────────────────────
Step 1a  detect_blocks          Detect format, classify every row
                                → output_docs/1_mapping/block_detection/

Step 1b  map_blocks             Exact-match lookup against the rulebook
                                → output_docs/1_mapping/auto_mapped/

Step 1c  find_mapping           AI fallback for unmatched rows (provider via llm_client.py)
                                → output_docs/1_mapping/ai_mapped/

Step 2a  extract_actual_noi     Logical substep inside compute_noi.py
                                → output_docs/2_noi_verification/actual_noi/

Step 2b  compute_noi            Same script computes NOI from mapped rows
                                → output_docs/2_noi_verification/computed_noi/

Step 2c  compare_noi            Month-by-month diff, PASS/FAIL verdict
                                → output_docs/2_noi_verification/comparison/
```

---

## Source Data

| Folder | Contents | Count |
|---|---|---|
| `data/input_T12_docs/` | Raw vendor T12 `.xlsx` files to process | 7 (test set) |
| `data/mapped_T12_docs/t12_docs/` | Human-reviewed `.xlsm` files (batch 1) | 6 |
| `data/mapped_T12_docs/new_t12_docs/` | Human-reviewed `.xlsm` files (batch 2) | 13 |
| `data/client_review_docs/` | Local working copy of the client-reviewed conflict workbook | 1 |

The 19 `.xlsm` files in `mapped_T12_docs/` are the training data for the rulebook —
they have been reviewed and corrected by a human analyst. The 7 `.xlsx` files in
`input_T12_docs/` are the test set that the pipeline processes. The reviewed
conflict workbook is also kept locally under `data/client_review_docs/` so the
rulebook build does not depend on paths outside `logic/mapping_rulebook/`.

---

## Prerequisites

```txt
Python 3.10+
openpyxl
langchain
langchain-openai
langchain-google-genai
pydantic
python-dotenv
```

A `.env` file at `logic/mapping_rulebook/.env` with the provider-specific keys used by `llm/llm_client.py`.

Common options:
```txt
OPENAI_API_KEY_AI_MAPPING=your_key_here
OPENAI_MODEL=gpt-5-nano

# Optional if switching provider
GOOGLE_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash-lite

# Optional if using LM Studio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=qwen/qwen2.5-coder-14b
```

---

## How to Run

All commands are run from `logic/mapping_rulebook/`.

### Master runner

```bash
python run_pipeline.py --stages 0,1,2
python run_pipeline.py --stages 1,2
python run_pipeline.py --from-stage 1 --to-stage 2
python run_pipeline.py --from-stage 0 --to-stage 2
python run_pipeline.py --stages 1 --ai-limit 5
```

This runner uses the stage runners internally and supports:
- running the whole pipeline
- running selected numbered stages
- continuing from a later stage
- requiring an explicit stage selection every time, so the run scope is always clear

### Stage runners

```bash
python pipeline/0_build_rulebook/run_stage.py

python pipeline/1_mapping/run_stage.py
python pipeline/1_mapping/run_stage.py --ai-limit 5

python pipeline/2_noi_verification/run_stage.py
```

### One-time rulebook build

```bash
# Step 1 — build phase-1 client-reviewed decisions
python pipeline/0_build_rulebook/build_client_review_rules.py

# Support step — extract reviewed-row history for later no_conflict work
python pipeline/0_build_rulebook/extract_reviewed_row_history.py

# Support step — learn section-side inference support from reviewed history
python pipeline/0_build_rulebook/build_section_side_support.py

# Support step — split historical layer into no_conflict + conflicts
python pipeline/0_build_rulebook/build_historical_rule_support.py

# Support step — build merged runtime rulebook artifact
python pipeline/0_build_rulebook/build_rulebook.py

# Step 4 — classify categories as REVENUE / EXPENSE / SKIP
python pipeline/0_build_rulebook/category_config.py
```

### Per-file processing

```bash
# Place raw .xlsx files in data/input_T12_docs/

python pipeline/1_mapping/detect_blocks.py
python pipeline/1_mapping/map_blocks.py
python pipeline/1_mapping/find_mapping.py

python pipeline/2_noi_verification/compute_noi.py
python pipeline/2_noi_verification/compare_noi.py
```

### Export to Excel (on demand)

```bash
python pipeline/utils/ai_results_to_excel.py   # final mapped files → styled Excel
python pipeline/utils/results_to_excel.py       # auto-mapped only → styled Excel
python pipeline/utils/convert_rulebook_to_excel.py  # rulebook → flat Excel
```

---

## Key Files

| File | Role |
|---|---|
| `db/mapping_rule_book.json` | Read-only rulebook snapshot area if we want to bless a build later |
| `output_docs/<date>/0_build_rulebook/client_review_rules/client_review_rulebook_phase1.json` | Phase-1 client review decisions: certain / contextual / unresolved |
| `output_docs/<date>/0_build_rulebook/reviewed_row_history/reviewed_row_history_index.json` | Historical row-context index extracted from the 19 reviewed `.xlsm` files |
| `output_docs/<date>/0_build_rulebook/section_side_support/section_side_support.json` | Learned exact section-path and section-name support used for contextual statement-side matching in Stage 1 |
| `output_docs/<date>/0_build_rulebook/historical_rule_support/no_conflict_rulebook.json` | Stable single-mapping descriptions derived from reviewed `.xlsm` history |
| `output_docs/<date>/0_build_rulebook/historical_rule_support/historical_conflicts.json` | Historical conflict descriptions enriched with client-review bucket info |
| `output_docs/<date>/0_build_rulebook/mapping_rulebook/mapping_rule_book.json` | Current runtime rulebook with `certain / contextual / no_conflict / unresolved` sections |
| `output_docs/<date>/0_build_rulebook/category_config/category_classification.json` | REVENUE / EXPENSE / SKIP classification used by NOI verification |
| `config/paths.py` | All file paths — single source of truth for directories and output locations |
| `config/rulebook_runtime.py` | One-place config for the current runtime rulebook path and Stage 0 builder chain |
| `config/agent_llm_config.py` | One-place config for agent-to-model/provider mapping |
| `llm/llm_client.py` | Shared LLM factory that reads the agent config and builds the correct client |

---

## NOI Formula

```
NOI = sum of all REVENUE-bucket row values
    − sum of all EXPENSE-bucket row values

SKIP rows (Capex categories) are excluded — they appear below the NOI line.
```

Verification tolerance: `max($1.00, 0.1% of actual NOI)` per month.
A file PASSES only if every month and the annual total are within tolerance.

---

## Folder Structure

```
mapping_rulebook/
├── run_pipeline.py      Master runner for numbered stages
├── pipeline/           Main pipeline scripts (numbered by stage)
│   ├── 0_build_rulebook/
│   │   ├── run_stage.py
│   │   ├── build_client_review_rules.py
│   │   ├── extract_reviewed_row_history.py
│   │   ├── build_section_side_support.py
│   │   ├── build_historical_rule_support.py
│   │   └── build_rulebook.py
│   ├── 1_mapping/
│   │   └── run_stage.py
│   ├── 2_noi_verification/
│   │   └── run_stage.py
│   └── utils/
├── analysis/           Diagnostic scripts — read-only, not part of pipeline
├── config/             paths, runtime rulebook config, and agent model config
├── data/               Input files (raw xlsx + human-reviewed xlsm)
├── db/                 Read-only reference snapshots
├── llm/                LLM client wrapper
├── output_docs/        All pipeline outputs (mirrors pipeline/ numbering)
└── docs/               Documentation
```

See [CONTEXT.md](CONTEXT.md) for the complete folder tree with all files listed,
per-script input/output specs, and run commands.
See [LOGIC.md](LOGIC.md) for how each algorithm works internally.

---

## Internal Docs

| File | Purpose |
|---|---|
| [WORKING_STYLE.md](WORKING_STYLE.md) | Repo-specific coding style: single-item modules, fail-hard behavior, and runner-later orchestration |
| [DECISIONS.md](DECISIONS.md) | Short decision log for structural choices and why they were made |
| [`audits/`](audits/) | Dated system-state audits so project context survives across coding sessions |
