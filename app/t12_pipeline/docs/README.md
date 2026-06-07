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
| `1_detection/block_detection/*.json` | Every row classified as data / header / subtotal / empty, with `statement_side` and annotation flags |
| `1_detection/annotated_blocks/*.json` | Same, plus `is_total_revenue`, `is_total_expense`, `is_noi` booleans |
| `1_detection/noi_verification/` | Vendor NOI, computed NOI, and month-by-month PASS/FAIL comparison |
| `2_mapping/auto_mapped/*.json` | DATA rows with rulebook mapping applied |
| `2_mapping/ai_mapped/*.json` | Unmapped rows filled in by AI; final file ready for analysis |

---

## Pipeline Overview

```
ONE-TIME (run when new reviewed .xlsm files arrive)
────────────────────────────────────────────────────
src/build_rulebook/run.py
    Merges client-reviewed decisions + historical row data
    → db/rulebooks/mapping_rulebook_<timestamp>.json


PER RUN (all three stages)
────────────────────────────────────────────────────
Stage 0  0_manifest/runner.py
    Picks latest rulebook from db/rulebooks/, embeds it + all paths + AI config
    → output_docs/current_manifest.json  (always-latest pointer)
    → output_docs/<timestamp>/run_manifest.json  (frozen per-run snapshot)

Stage 1  1_detection/run_stage.py
    1a  detect_blocks    → block_detection/    (classify every row, assign statement_side)
    1b  annotate_totals  → annotated_blocks/   (stamp is_total_revenue/expense/noi flags)
    1c  compute_noi      → noi_verification/actual_noi/ + computed_noi/
    1d  compare_noi      → noi_verification/comparison/  (PASS/FAIL per month)

Stage 2  2_mapping/run_stage.py
    2a  map_blocks    → auto_mapped/   (exact rulebook lookup)
    2b  find_mapping  → ai_mapped/    (AI fallback for unmatched rows)
```

**NOI formula:** `NOI = sum(revenue rows) − sum(expense rows)` — capex rows excluded.
**Tolerance:** `max($1.00, 0.1% of actual NOI)` per month.

---

## How to Run

All commands from `app/t12_pipeline/`.

```bash
# Build rulebook (run once when new .xlsm files arrive)
python src/build_rulebook/run.py

# Full pipeline
python src/pipeline/run_pipeline.py --stages 0,1,2

# Most common: reuse existing manifest, run detection + mapping
python src/pipeline/run_pipeline.py --stages 1,2

# Limit AI calls while testing
python src/pipeline/run_pipeline.py --stages 1,2 --ai-limit 5

# Individual stages
python src/pipeline/0_manifest/runner.py
python src/pipeline/1_detection/run_stage.py
python src/pipeline/2_mapping/run_stage.py

# Export to Excel (on demand)
python src/pipeline/utils/auto_mapped_to_excel.py
python src/pipeline/utils/ai_mapped_to_excel.py
python src/pipeline/utils/convert_rulebook_to_excel.py
```

---

## Source Data

| Folder | Contents | Count |
|---|---|---|
| `data/input_T12_docs/` | Raw vendor T12 `.xlsx` files to process | 7 (test set) |
| `data/mapped_T12_docs/` | Human-reviewed `.xlsm` files (training set for the rulebook) | 19 |
| `data/client_review_docs/` | Local copy of the client-reviewed conflict workbook | 1 |

The 19 `.xlsm` files are the training data for the rulebook — reviewed and corrected by a human analyst.

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

A `.env` file at `app/t12_pipeline/.env` with provider-specific keys used by `llm/llm_client.py`.

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

## Folder Structure

```
app/t12_pipeline/
├── src/
│   ├── build_rulebook/         ← one-time tool (not part of pipeline)
│   │   └── run.py
│   ├── config/
│   │   ├── paths.py            ← all paths, single source of truth
│   │   ├── rulebook_runtime.py ← build_rulebook script list + output path
│   │   ├── rulebook_utils.py   ← load/validate/flatten helpers
│   │   └── agent_llm_config.py ← agent → provider/model mapping
│   ├── llm/
│   │   └── llm_client.py       ← LLM client wrapper
│   └── pipeline/
│       ├── 0_manifest/         ← Stage 0: writes current_manifest.json
│       ├── 1_detection/        ← Stage 1: detect → annotate → NOI verify
│       │   └── formats/        ← per-format row classifiers
│       ├── 2_mapping/          ← Stage 2: rulebook map → AI fallback
│       ├── utils/              ← export scripts, not part of main pipeline
│       └── run_pipeline.py     ← master stage runner
├── data/
│   ├── input_T12_docs/         ← raw .xlsx files (read-only)
│   └── mapped_T12_docs/        ← human-reviewed .xlsm files (training data)
├── db/
│   └── rulebooks/              ← versioned rulebook snapshots (build_rulebook output)
├── output_docs/
│   ├── current_manifest.json   ← always-latest pointer
│   └── <timestamp>/
│       ├── run_manifest.json   ← frozen per-run snapshot
│       ├── 1_detection/
│       │   ├── block_detection/
│       │   ├── annotated_blocks/
│       │   └── noi_verification/
│       └── 2_mapping/
│           ├── auto_mapped/
│           └── ai_mapped/
└── docs/
    ├── README.md               ← this file
    ├── DECISIONS.md            ← structural decision log
    └── detection_logic/        ← per-format row classification decision trees
```

---

## Internal Docs

| File | Purpose |
|---|---|
| [DECISIONS.md](DECISIONS.md) | Short decision log for structural choices and why they were made |
| [detection_logic/](detection_logic/) | Per-format row classification decision trees with real row traces |
| [audits/](audits/) | Dated system-state audits |
