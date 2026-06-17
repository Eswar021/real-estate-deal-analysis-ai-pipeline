# T12 Mapping Pipeline — Context & Reference

> **ARCHIVED — 2026-05-15 snapshot, no longer maintained.**
> This file reflects the old pipeline structure (`0_build_rulebook`, `1_mapping`, `2_noi_verification`).
> The current architecture is documented in `CLAUDE.md`, `AGENTS.md`, and `docs/README.md`.
> The Three T12 File Formats and Statement Side Assignment sections below are still accurate.

Automated pipeline that reads raw Trailing-12-Month (T12) financial Excel files from property sellers,
classifies every row, maps each line item to Oakdale Capital's canonical chart-of-accounts categories,
and produces styled Excel reports for human review.

The pipeline runs in one direction: **classify → auto-map → AI fallback → export**.
No aggregation or analysis happens here — that is a later step.

---

## Pipeline Overview

```
[One-time / Rulebook Build]  pipeline/0_build_rulebook/
  build_client_review_rules  →  output_docs/0_build_rulebook/client_review_rules/
  extract_reviewed_row_history  →  output_docs/0_build_rulebook/reviewed_row_history/
  build_historical_rule_support  →  output_docs/0_build_rulebook/historical_rule_support/
  build_rulebook  →  output_docs/0_build_rulebook/mapping_rulebook/

[Per file — Mapping]  pipeline/1_mapping/
  detect_blocks        →  output_docs/1_mapping/block_detection/
  map_blocks           →  output_docs/1_mapping/auto_mapped/
  find_mapping         →  output_docs/1_mapping/ai_mapped/

[Per file — NOI Verification]  pipeline/2_noi_verification/
  compute_noi          →  output_docs/2_noi_verification/actual_noi/
                       →  output_docs/2_noi_verification/computed_noi/
  compare_noi          →  output_docs/2_noi_verification/comparison/

[Utilities — on demand]  pipeline/utils/
  auto_mapped_to_excel.py     →  output_docs/utils/auto_mapped_to_excel/
  ai_mapped_to_excel.py       →  output_docs/utils/ai_mapped_to_excel/
  convert_rulebook_to_excel.py  →  output_docs/utils/mapping_rule_book.xlsx
```

**NOI formula:**
`NOI = sum(REVENUE rows) − sum(EXPENSE rows)` — Capex rows are excluded.

---

## Folder Structure

```
mapping_rulebook/
├── run_pipeline.py                  Master runner for numbered stages
├── pipeline/
│   ├── runner_utils.py             Small shared runner helpers
│   ├── 0_build_rulebook/
│   │   ├── build_client_review_rules.py  Phase 1 — client-reviewed certain/contextual/unresolved
│   │   ├── extract_reviewed_row_history.py  Historical reviewed-row context extraction
│   │   ├── build_historical_rule_support.py  Build no_conflict + historical conflicts support
│   │   ├── build_rulebook.py         Merge current sections into one runtime-ready artifact
│   │   └── run_stage.py              Stage 0 runner
│   ├── 1_mapping/
│   │   ├── detect_blocks.py          Classify rows in raw T12 .xlsx files
│   │   ├── map_blocks.py             Auto-map DATA rows using rulebook (exact match)
│   │   ├── find_mapping.py           AI fallback — LangChain structured output via llm_client.py
│   │   ├── prompt.txt                System prompt — AI must choose from existing categories only
│   │   └── run_stage.py              Stage 1 runner
│   ├── 2_noi_verification/
│   │   ├── compute_noi.py            Extract actual NOI + compute NOI from mapped rows
│   │   ├── compare_noi.py            PASS/FAIL diff: actual vs computed NOI
│   │   └── run_stage.py              Stage 2 runner
│   └── utils/
│       ├── auto_mapped_to_excel.py       Export auto_mapped JSON → styled Excel
│       ├── ai_mapped_to_excel.py         Export ai_mapped JSON → styled Excel with AI columns
│       └── convert_rulebook_to_excel.py  Export rulebook JSON → flat Excel for client review
│
├── analysis/                         Diagnostic notebooks — read-only, not part of pipeline
│   ├── conflict_analysis.ipynb
│   └── inspection.ipynb
│
├── config/
│   ├── paths.py                      All file paths — import from here, never hardcode
│   ├── rulebook_runtime.py           Central config for the current runtime rulebook
│   ├── rulebook_utils.py             Load/validate/flatten rulebook helpers
│   └── agent_llm_config.py           Central config for agent → provider/model mapping
│
├── data/
│   ├── input_T12_docs/               Raw vendor T12 .xlsx files (7 files — test set)
│   ├── client_review_docs/           Local copy of the client-reviewed conflict workbook
│   └── mapped_T12_docs/
│       ├── t12_docs/                 6 older human-reviewed .xlsm files (batch 1)
│       └── new_t12_docs/             13 newer human-reviewed .xlsm files (batch 2)
│
├── db/
│   └── mapping_rule_book.json        Read-only rulebook snapshot area
│
├── llm/
│   ├── llm_client.py                 LLM client wrapper (Gemini / OpenAI / LM Studio)
│   └── llm_testing.py                Test harness for LLM calls
│
├── output_docs/
│   ├── 0_build_rulebook/
│   │   ├── reviewed_row_history/     Historical row-context extraction from reviewed `.xlsm` files
│   │   ├── historical_rule_support/  no_conflict and historical conflict support outputs
│   │   ├── mapping_rulebook/         current runtime rulebook build output
│   │   └── client_review_rules/      client_review_rulebook_phase1.json
│   ├── 1_mapping/
│   │   ├── block_detection/          JSON from detect_blocks
│   │   ├── auto_mapped/              JSON from map_blocks
│   │   ├── ai_mapped/                JSON from find_mapping
│   │   └── ai_mapping_logs/          Full LLM prompt + response per AI call
│   ├── 2_noi_verification/
│   │   ├── actual_noi/               Vendor-reported NOI values
│   │   ├── computed_noi/             Our computed NOI from mapped rows
│   │   └── comparison/               PASS/FAIL diff report
│   └── utils/
│       ├── auto_mapped_to_excel/     Styled Excel from auto_mapped_to_excel.py
│       ├── ai_mapped_to_excel/       Styled Excel from ai_mapped_to_excel.py
│       └── mapping_rule_book.xlsx    Flat rulebook export
│
└── docs/
    ├── README.md                     Overview and run guide
    ├── CONTEXT.md                    This file
    ├── DECISIONS.md                  Structural decision log
    └── audits/                       Dated system audits
```

---

## Three T12 File Formats

Vendor T12 files come in three structural layouts. The format is auto-detected on the first 60 rows.

### Format A — Code in Col A, Description in Col B
*Properties: Willows of Coventry, Pointe Inverness, Carmel Woods*

```
Col A           Col B                         Classification
─────────────   ─────────────────────────     ─────────────
INCOME          (empty)                    →  HEADER
4002-0000         Gross Potential          →  DATA  (code in A; description from B)
4110-0000         Month to Month           →  DATA
(empty)         TOTAL DEDUCTIONS           →  SUBTOTAL
4999-9999       NET RENTAL REVENUE         →  SUBTOTAL  (code ending in 9999)
```

| Signal | Classification |
|---|---|
| Col A matches `DDDD-DDDD` pattern and col B is not a total | DATA |
| Col A has text, Col B empty | HEADER |
| Col A empty, Col B has text | SUBTOTAL |
| Account code ends in `9999` | SUBTOTAL |
| Col A has code + col B is total text | SUBTOTAL |

---

### Format B — Embedded Code in Col A
*Properties: Brownsburg Crossing, Pebble Brook Village*

```
Col A                                    Classification
────────────────────────────────────     ─────────────
  Rental Income                       →  HEADER
    5120 - Gross Possible Rent         →  DATA   (code stripped from description)
  Total Possible Rent                  →  SUBTOTAL
  Customer Support Team Salaries       →  DATA   (deep indent ≥ 6 spaces, no code)
```

| Signal | Classification |
|---|---|
| Text matches `DDDD - ...` pattern | DATA |
| Starts with "Total" or matches total keywords | SUBTOTAL |
| Deep indent (> 4 spaces) without code | DATA |
| Everything else | HEADER |

---

### Format C — No Codes, Indent-Based
*Properties: Echo Park at Perry Crossing*

```
Col A                                    Indent   Classification
────────────────────────────────────     ──────   ─────────────
Rental Revenue                           0      →  HEADER
  Gross Potential                         2      →  DATA
Adjusted Gross Possible Revenue          0      →  SUBTOTAL (indent=0 + has numbers)
Total Rental Reductions                  0      →  SUBTOTAL (starts with "Total")
```

| Signal | Classification |
|---|---|
| Starts with "Total" | SUBTOTAL |
| Indent ≥ 2 spaces | DATA |
| Indent = 0 + has numeric values | SUBTOTAL |
| Indent = 0 + no numbers | HEADER |

---

## Statement Side Assignment

`statement_side` is assigned structurally via a two-flag state machine in `detect_blocks.py`:

- Flip `income_phase_complete` when a subtotal matches grand income total markers
  (`total income`, `total revenue`, `effective gross income`, `total operating revenues`)
- Flip `capex_phase_complete` when a subtotal contains `net operating income`
  (only checked after income flip — guards against summary rows at top of some files)
- Data rows before income flip → `revenue`, after → `expense`, after NOI flip → `capex`
- Capex rows are excluded from all mapping and NOI computation

---

## Rulebook

**Configured active path:** controlled by `config/rulebook_runtime.py`
**Runtime rulebook output:** `output_docs/<date>/0_build_rulebook/mapping_rulebook/`
**db/mapping_rule_book.json:** read-only reference snapshot

**Runtime structure:**
- `{ certain, contextual, no_conflict, unresolved }`

**Lookup behavior:**
1. `certain`
2. `contextual`
3. `no_conflict`
4. `unresolved` → AI

Rows not found flow forward with `"not_found": true` and go to the AI stage.

---

## Pipeline Scripts

---

### `0_build_rulebook/` — Rulebook Build

#### `build_client_review_rules.py`

Reads the client-reviewed conflict workbook and classifies the reviewed conflict
descriptions into three sections: `certain`, `contextual`, `unresolved`.

**Input:** `data/client_review_docs/conflict_sources_report_v2_J VM Notes.xlsx`
**Output:** `output_docs/0_build_rulebook/client_review_rules/client_review_rulebook_phase1.json`

---

#### `extract_reviewed_row_history.py`

Reads the 19 reviewed `.xlsm` mapping docs and extracts enriched data-row history
for later `no_conflict` / conflict work. Each extracted row keeps:
`row_description`, `statement_side`, `section_path`, `nearest_section`,
`auto_mapping`, `override`, `final_mapping`, `source_type`.

**Input:** `.xlsm` files from `data/mapped_T12_docs/`
**Output:** `output_docs/0_build_rulebook/reviewed_row_history/`

---

#### `build_historical_rule_support.py`

Reads the reviewed-row history index and the phase-1 client-reviewed decisions,
then splits the historical layer into `no_conflict_rulebook.json` and
`historical_conflicts.json`.

**Input:** `output_docs/0_build_rulebook/client_review_rules/` + `reviewed_row_history/`
**Output:** `output_docs/0_build_rulebook/historical_rule_support/`

---

#### `build_rulebook.py`

Reads the already-built support artifacts and merges them into one sectioned
runtime rulebook: `{ certain, contextual, no_conflict, unresolved }`.

**Input:** `output_docs/0_build_rulebook/client_review_rules/` + `historical_rule_support/`
**Output:** `output_docs/0_build_rulebook/mapping_rulebook/mapping_rule_book.json`

---

### `1_mapping/` — Per-file Mapping

#### `detect_blocks.py`

Classifies every row in a raw T12 `.xlsx` file as `header`, `data`, `subtotal`, or `empty`.
Values (monthly numbers) are captured for both DATA and SUBTOTAL rows.

**Input:** `data/input_T12_docs/*.xlsx`
**Output:** `output_docs/1_mapping/block_detection/<filename>.json`

---

#### `map_blocks.py`

Exact-match (case-insensitive) lookup of every DATA row description against the runtime rulebook.

**Input:** `output_docs/1_mapping/block_detection/` + runtime rulebook from `config/rulebook_runtime.py`
**Output:** `output_docs/1_mapping/auto_mapped/`

---

#### `find_mapping.py`

Calls the configured LLM provider for every row with `not_found: true`. Returns a structured suggestion.
AI must choose only from the existing canonical category list — new names are forbidden.

**Input:** `output_docs/1_mapping/auto_mapped/*.json`
**Output:** `output_docs/1_mapping/ai_mapped/` + `output_docs/1_mapping/ai_mapping_logs/`

---

### `2_noi_verification/` — NOI Verification

Runs after `find_mapping.py`. Tolerance: `max($1.00, 0.1% of actual NOI)`.

#### `compute_noi.py`

1. Extracts vendor-reported NOI from the ai_mapped subtotal rows.
2. Computes NOI from mapped DATA rows — revenue rows sum, expense rows subtract, capex rows excluded.

**Input:** `output_docs/1_mapping/ai_mapped/*.json`
**Output:** `output_docs/2_noi_verification/actual_noi/` + `output_docs/2_noi_verification/computed_noi/`

---

#### `compare_noi.py`

Month-by-month diff. PASS if every month and annual total are within tolerance.

**Input:** `output_docs/2_noi_verification/actual_noi/` + `output_docs/2_noi_verification/computed_noi/`
**Output:** `output_docs/2_noi_verification/comparison/`

---

### `utils/` — Export Utilities

Not part of the main pipeline flow — run on demand.

| Script | Input | Output |
|---|---|---|
| `auto_mapped_to_excel.py` | `1_mapping/auto_mapped/` | `utils/auto_mapped_to_excel/` |
| `ai_mapped_to_excel.py` | `1_mapping/ai_mapped/` | `utils/ai_mapped_to_excel/` |
| `convert_rulebook_to_excel.py` | runtime rulebook from `config/rulebook_runtime.py` | `utils/mapping_rule_book.xlsx` |

---

## LLM Configuration

**LLM provider:** Configurable via `config/agent_llm_config.py` and resolved by `llm/llm_client.py`

Supported options (selected via `.env` and code-level provider choice):
- OpenAI GPT models
- Gemini models
- LM Studio local model

---

## Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Block detection approach | Flat row-by-row | Hierarchical nesting was fragile across 3 formats; flat + `section_context` is sufficient |
| Fuzzy matching | Not implemented | LLM fallback handles variants; exact match keeps false-positives at zero |
| Subtotal values in detect_blocks | Captured | NOI verification needs vendor-reported NOI subtotal for comparison |
| Capex excluded from NOI | Structural flip flag | Capex rows appear below the NOI line; detected by `net operating income` subtotal |
| AI prompt — category constraint | Must pick from existing list | Prevents LLM from inventing categories that silently miss classification |
| NOI tolerance | `max($1.00, 0.1% of actual)` | Absorbs rounding without masking real mapping errors |
| Folder structure | Numbered pipeline folders | Order is visible from directory listing; no ambiguity about sequence |
| Runtime rulebook config | `config/rulebook_runtime.py` | Keep one current rulebook path and one current Stage 0 builder chain in one place |
| Agent LLM selection | `config/agent_llm_config.py` | Keep provider/model choice centralized per agent |
