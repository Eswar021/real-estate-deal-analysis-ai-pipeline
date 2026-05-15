# T12 Mapping Pipeline — Context & Reference

Automated pipeline that reads raw Trailing-12-Month (T12) financial Excel files from property sellers,
classifies every row, maps each line item to Oakdale Capital's canonical chart-of-accounts categories,
and produces styled Excel reports for human review.

The pipeline runs in one direction: **classify → auto-map → AI fallback → export**.
No aggregation or analysis happens here — that is a later step.

---

## Pipeline Overview

```
[One-time / Rulebook Build]  pipeline/0_build_rulebook/
  extract_mappings_v2  →  output_docs/0_build_rulebook/extracted_mappings_v2/
  build_rulebook_v2    →  output_docs/0_build_rulebook/mapping_rulebook_v2/
  build_client_review_rules  →  output_docs/0_build_rulebook/client_review_rules/
  extract_reviewed_row_history  →  output_docs/0_build_rulebook/reviewed_row_history/
  build_historical_rule_support  →  output_docs/0_build_rulebook/historical_rule_support/
  build_rulebook_v3  →  output_docs/0_build_rulebook/mapping_rulebook_v3/
  category_config      →  output_docs/0_build_rulebook/category_config/

[Per file — Mapping]  pipeline/1_mapping/
  detect_blocks        →  output_docs/1_mapping/block_detection/
  map_blocks           →  output_docs/1_mapping/auto_mapped/
  find_mapping         →  output_docs/1_mapping/ai_mapped/

[Per file — NOI Verification]  pipeline/2_noi_verification/
  compute_noi          →  output_docs/2_noi_verification/actual_noi/
                       →  output_docs/2_noi_verification/computed_noi/
  compare_noi          →  output_docs/2_noi_verification/comparison/

[Utilities — on demand]  pipeline/utils/
  results_to_excel     →  output_docs/utils/auto_mapped_to_excel/
  ai_results_to_excel  →  output_docs/utils/ai_mapped_to_excel/
  convert_rulebook_to_excel  →  output_docs/utils/mapping_rule_book.xlsx
```

**Final Mapping rule (applied during human review in .xlsm files):**
`Final_Mapping = OVERRIDE if human entered one, otherwise Auto Mapping`

**NOI formula:**
`NOI = sum(REVENUE rows) − sum(EXPENSE rows)` — SKIP rows (Capex) are excluded.

---

## Folder Structure

```
mapping_rulebook/
├── run_pipeline.py                  Master runner for numbered stages
├── pipeline/
│   ├── runner_utils.py             Small shared runner helpers
│   ├── 0_build_rulebook/
│   │   ├── create_mappings.py        v1 — build rulebook from Final_Mapping only (kept for reference)
│   │   ├── extract_mappings_v2.py    v2 Step 1 — extract rows with auto/override/final per row
│   │   ├── build_rulebook_v2.py      v2 Step 2 — conflict-resolved rulebook, override-priority logic
│   │   ├── build_client_review_rules.py  Phase 1 — client-reviewed certain/contextual/unresolved
│   │   ├── extract_reviewed_row_history.py  Historical reviewed-row context extraction
│   │   ├── build_historical_rule_support.py  Build no_conflict + historical conflicts support
│   │   ├── build_rulebook_v3.py      Merge v3 sections into one runtime-ready artifact
│   │   ├── category_config.py        Classify each category as REVENUE / EXPENSE / SKIP
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
│       ├── results_to_excel.py       Export auto_mapped JSON → styled Excel
│       ├── ai_results_to_excel.py    Export ai_mapped JSON → styled Excel with AI columns
│       └── convert_rulebook_to_excel.py  Export rulebook JSON → flat Excel for inspection
│
├── analysis/                         Diagnostic scripts — read-only, not part of pipeline
│   ├── conflict_test.py              Tests rulebook-first proposal (result: rejected for headers)
│   ├── find_rulebook_duplicates.py   Finds descriptions in 2+ categories in v1 rulebook
│   ├── find_conflict_sources.py      Traces each duplicate back to its source .xlsm file
│   └── conflict_sources_to_excel.py  Generates two-tab Excel conflict report for client
│
├── config/
│   ├── paths.py                      All file paths — import from here, never hardcode
│   ├── rulebook_runtime.py           Central switch for active runtime rulebook profile
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
│   ├── mapping_rule_book.json        v1 rulebook snapshot — read-only reference
│   ├── mapping_rule_book_v2.json     v2 rulebook snapshot — read-only reference
│   └── category_classification.json  older classification snapshot — read-only reference
│
├── llm/
│   ├── llm_client.py                 LLM client wrapper (Gemini / OpenAI / LM Studio)
│   └── llm_testing.py                Test harness for LLM calls
│
├── output_docs/
│   ├── 0_build_rulebook/
│   │   ├── extracted_mappings_v2/    Per-file JSON from extract_mappings_v2 (one per .xlsm)
│   │   ├── reviewed_row_history/     Historical row-context extraction from reviewed `.xlsm` files
│   │   ├── historical_rule_support/  no_conflict and historical conflict support outputs
│   │   ├── mapping_rulebook_v1/      mapping_rule_book.json from the v1 builder
│   │   ├── mapping_rulebook_v2/      mapping_rule_book_v2.json + rulebook_v2_audit.json
│   │   ├── mapping_rulebook_v3/      merged v3 rulebook with sectioned runtime structure
│   │   ├── client_review_rules/      client_review_rulebook_phase1.json
│   │   └── category_config/          category_classification.json used by Stage 2
│   ├── 1_mapping/
│   │   ├── block_detection/          JSON from detect_blocks
│   │   ├── auto_mapped/              JSON from map_blocks
│   │   ├── ai_mapped/                JSON from find_mapping
│   │   └── ai_mapping_logs/          Full LLM prompt + response per AI call
│   ├── 2_noi_verification/
│   │   ├── actual_noi/               Vendor-reported NOI values
│   │   ├── computed_noi/             Our computed NOI from mapped rows
│   │   └── comparison/               PASS/FAIL diff report
│   ├── utils/
│   │   ├── auto_mapped_to_excel/     Styled Excel from results_to_excel
│   │   ├── ai_mapped_to_excel/       Styled Excel from ai_results_to_excel
│   │   └── mapping_rule_book.xlsx    Flat rulebook export
│   └── analysis/                     All outputs from analysis/ scripts (JSON, Excel)
│
└── docs/
    ├── README.md                     Overview and run guide
    ├── CONTEXT.md                    This file
    ├── LOGIC.md                      Algorithm reference
    ├── WORKING_STYLE.md              Repo-specific coding style
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
| Col A matches `DDDD-DDDD` pattern | DATA |
| Col A has text, Col B empty | HEADER |
| Col A empty, Col B has text | SUBTOTAL |
| Account code ends in `9999` | SUBTOTAL (Carmel Woods) |

---

### Format B — Embedded Code in Col A
*Properties: Brownsburg Crossing, Pebble Brook Village*

```
Col A                                    Classification
────────────────────────────────────     ─────────────
  Rental Income                       →  HEADER
    5120 - Gross Possible Rent         →  DATA   (code stripped from description)
  Total Possible Rent                  →  SUBTOTAL
```

| Signal | Classification |
|---|---|
| Text matches `DDDD - ...` pattern | DATA |
| Starts with "Total" | SUBTOTAL |
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

## Rulebook

**Configured active path:** controlled by `config/rulebook_runtime.py`
**Runtime rulebook outputs:** `output_docs/<date>/0_build_rulebook/mapping_rulebook_v1/` and `mapping_rulebook_v2/`
**db copies:** kept as read-only reference snapshots

**Structure:** `{ canonical_category: [vendor_description_variants, ...] }`

**Current state (v2):** ~1,690 entries across 36 canonical categories.
Built from 19 human-reviewed `.xlsm` files (6 in `t12_docs/` + 13 in `new_t12_docs/`).

**Lookup:** Reverse-map built at runtime (`description_lower → category`, exact match).
Rows not found → `"not_found": true` → passed to AI agent.

**V2 vs V1:**
V1 reads only `Final_Mapping` — last file processed wins on conflict.
V2 captures `Auto Mapping`, `OVERRIDE`, and `Final_Mapping` per row, then resolves conflicts with override-priority logic (see pipeline/0_build_rulebook below).

---

## Category Classification

**Path:** `output_docs/<date>/0_build_rulebook/category_config/category_classification.json`
**Script:** `pipeline/0_build_rulebook/category_config.py`

| Bucket | Count | Meaning |
|---|---|---|
| `REVENUE` | 16 | Top-line income and adjustments |
| `EXPENSE` | 17 | Operating expenses that factor into NOI |
| `SKIP` | 3 | Below-NOI-line Capex — excluded from NOI calculation |

Re-run after adding new categories to the rulebook:
```bash
python pipeline/0_build_rulebook/category_config.py
```

---

## Pipeline Scripts

---

### `0_build_rulebook/` — Rulebook Build

#### `extract_mappings_v2.py` — Step 1

Reads all 19 `.xlsm` source files. For each data row extracts:

| Field | Meaning |
|---|---|
| `row_description` | Vendor account name |
| `auto_mapping` | Algorithm-suggested category |
| `override` | Human correction (null if auto was accepted) |
| `final_mapping` | Effective mapping |
| `source_type` | `"override"` or `"auto"` |

Stops at the first empty Index column cell and only processes `str` values — numeric/boolean formula results are discarded.

```bash
python pipeline/0_build_rulebook/extract_mappings_v2.py
```
**Input:** `.xlsm` files from `data/mapped_T12_docs/`
**Output:** `output_docs/0_build_rulebook/extracted_mappings_v2/<filename>.json`

---

#### `build_rulebook_v2.py` — Step 2

Resolves conflicts using source-type priority:

| Conflict type | Resolution |
|---|---|
| All files agree | `clean` — accepted as-is |
| Override vs Auto | `override_resolved` — override wins |
| Override vs Override | `override_conflict` — most common override wins; flagged in audit |
| Auto vs Auto | `auto_conflict` — majority vote; `auto_tie` if tied |

Outputs to `output_docs/` only — **never writes directly to `db/`**.

```bash
python pipeline/0_build_rulebook/build_rulebook_v2.py
```
**Input:** `output_docs/0_build_rulebook/extracted_mappings_v2/` + `db/mapping_rule_book_v2.json` (baseline, optional)
**Output:** `output_docs/0_build_rulebook/mapping_rulebook_v2/mapping_rule_book_v2.json` + `rulebook_v2_audit.json`

---

#### `build_client_review_rules.py` — Phase 1 reviewed decisions

Reads the client-reviewed conflict workbook and classifies the 94 reviewed conflict
descriptions into three sections only:

- `certain`
- `contextual`
- `unresolved`

This phase intentionally does not read the 19 reviewed `.xlsm` mapping docs yet.
The later `no_conflict` phase is kept separate so the client-reviewed decisions do
not get mixed with historical extraction logic.

```bash
python pipeline/0_build_rulebook/build_client_review_rules.py
```
**Input:** `data/client_review_docs/conflict_sources_report_v2_J VM Notes.xlsx`
**Output:** `output_docs/0_build_rulebook/client_review_rules/client_review_rulebook_phase1.json`

---

#### `extract_reviewed_row_history.py` — Historical row-context extraction

Reads the 19 reviewed `.xlsm` mapping docs and extracts enriched data-row history
for later `no_conflict` / conflict work. Each extracted row keeps:

- `row_description`
- `statement_side`
- `section_path`
- `nearest_section`
- `auto_mapping`
- `override`
- `final_mapping`
- `source_type`

This script intentionally does not build the final runtime rulebook yet. It is a
support builder so later stages can derive `no_conflict` and historical conflict
metadata without reparsing all reviewed workbooks.

```bash
python pipeline/0_build_rulebook/extract_reviewed_row_history.py
```
**Input:** `.xlsm` files from `data/mapped_T12_docs/`
**Output:** `output_docs/0_build_rulebook/reviewed_row_history/per_file/<filename>.json`
and `output_docs/0_build_rulebook/reviewed_row_history/reviewed_row_history_index.json`

---

#### `build_historical_rule_support.py` — no_conflict + conflict support

Reads the reviewed-row history index and the phase-1 client-reviewed decisions,
then splits the historical layer into two outputs:

- `no_conflict_rulebook.json`
- `historical_conflicts.json`

`no_conflict_rulebook.json` contains the descriptions that only ever mapped to one
final category across the 19 reviewed `.xlsm` files.

`historical_conflicts.json` keeps the multi-mapping descriptions together with:

- historical mappings
- statement-side history
- section-path history
- client-review bucket (`certain`, `contextual`, or `unresolved`)
- the corresponding client-review entry

This keeps runtime-rule decisions separate from historical support context.

```bash
python pipeline/0_build_rulebook/build_historical_rule_support.py
```
**Input:** `output_docs/0_build_rulebook/client_review_rules/client_review_rulebook_phase1.json`
and `output_docs/0_build_rulebook/reviewed_row_history/reviewed_row_history_index.json`
**Output:** `output_docs/0_build_rulebook/historical_rule_support/no_conflict_rulebook.json`
and `output_docs/0_build_rulebook/historical_rule_support/historical_conflicts.json`

---

#### `build_rulebook_v3.py` — merged v3 rulebook

Reads the already-built support artifacts and merges them into one sectioned v3
rulebook with four runtime sections:

- `certain`
- `contextual`
- `no_conflict`
- `unresolved`

This is the first artifact that matches the intended new rulebook structure.
It is still kept separate from the active runtime profile for now, because the
current mapping stage still expects the older flat `category -> descriptions`
shape.

```bash
python pipeline/0_build_rulebook/build_rulebook_v3.py
```
**Input:** `output_docs/0_build_rulebook/client_review_rules/client_review_rulebook_phase1.json`
plus `output_docs/0_build_rulebook/historical_rule_support/*.json`
**Output:** `output_docs/0_build_rulebook/mapping_rulebook_v3/mapping_rule_book_v3.json`

---

#### `category_config.py`

Reads the active rulebook, classifies all categories, writes `output_docs/0_build_rulebook/category_config/category_classification.json`.
```bash
python pipeline/0_build_rulebook/category_config.py
```

---

### `1_mapping/` — Per-file Mapping

#### `detect_blocks.py`

Classifies every row in a raw T12 `.xlsx` file as `header`, `data`, `subtotal`, or `empty`.
Values (monthly numbers) are captured for both DATA and SUBTOTAL rows — required by NOI verification.

```bash
python pipeline/1_mapping/detect_blocks.py
```
**Input:** `data/input_T12_docs/*.xlsx`
**Output:** `output_docs/1_mapping/block_detection/<filename>.json`

---

#### `map_blocks.py`

Exact-match (case-insensitive) lookup of every DATA row description against the currently configured runtime rulebook.

```bash
python pipeline/1_mapping/map_blocks.py
```
**Input:** `output_docs/1_mapping/block_detection/` + runtime rulebook from `config/rulebook_runtime.py`
**Output:** `output_docs/1_mapping/auto_mapped/` — adds `mapping` and `not_found` to each row

---

#### `find_mapping.py`

Calls the configured LLM provider via LangChain for every row with `not_found: true`. Returns a structured suggestion.

> **Prompt constraint:** AI must choose only from the existing canonical category list. New category names are forbidden — prevents rulebook drift.

```bash
python pipeline/1_mapping/find_mapping.py
```
**Input:** `output_docs/1_mapping/auto_mapped/*.json`
**Output:** `output_docs/1_mapping/ai_mapped/` + `output_docs/1_mapping/ai_mapping_logs/`

---

### `2_noi_verification/` — NOI Verification

Runs after `find_mapping.py`. Tolerance: `max($1.00, 0.1% of actual NOI)`.

#### `compute_noi.py`

Handles both logical substeps in the current Stage 2 implementation:

1. Extract vendor-reported NOI from the ai_mapped subtotal rows
2. Compute NOI from mapped DATA rows using REVENUE / EXPENSE / SKIP buckets

`final_mapping = auto_mapping if found in rulebook, else ai_suggested_mapping`

```bash
python pipeline/2_noi_verification/compute_noi.py
```
**Input:** `output_docs/1_mapping/ai_mapped/*.json` + `output_docs/0_build_rulebook/category_config/category_classification.json`
**Output:** `output_docs/2_noi_verification/actual_noi/` + `output_docs/2_noi_verification/computed_noi/`

---

#### `compare_noi.py`

Month-by-month diff. PASS if every month and annual total are within tolerance.

```bash
python pipeline/2_noi_verification/compare_noi.py
```
**Input:** `output_docs/2_noi_verification/actual_noi/` + `output_docs/2_noi_verification/computed_noi/`
**Output:** `output_docs/2_noi_verification/comparison/`

---

### `utils/` — Export Utilities

Not part of the main pipeline flow — run on demand.

| Script | Input | Output |
|---|---|---|
| `results_to_excel.py` | `1_mapping/auto_mapped/` | `utils/auto_mapped_to_excel/` |
| `ai_results_to_excel.py` | `1_mapping/ai_mapped/` | `utils/ai_mapped_to_excel/` |
| `convert_rulebook_to_excel.py` | runtime rulebook from `config/rulebook_runtime.py` | `utils/mapping_rule_book.xlsx` |

---

### `analysis/` — Diagnostic Scripts

Read-only tools. Do not modify any pipeline data.
All outputs go to `output_docs/analysis/`.

**Run order for the conflict report:**
```bash
python analysis/find_rulebook_duplicates.py      # → output_docs/analysis/rulebook_duplicates.json
python analysis/find_conflict_sources.py         # → output_docs/analysis/conflict_file_sources_v2.json
python analysis/conflict_sources_to_excel.py     # → output_docs/analysis/conflict_sources_report_v2.xlsx
```

**Excel report tabs:**
- **Category Conflicts** — all 94 descriptions with multiple mappings (Description / Category / Source Files)
- **Revenue vs Expense** — 15 descriptions crossing REVENUE ↔ EXPENSE (adds Bucket column)

| Script | Purpose |
|---|---|
| `conflict_test.py` | Tested rulebook-first row detection — 27% header conflict rate → rejected |
| `find_rulebook_duplicates.py` | Finds descriptions in 2+ categories in v1 rulebook |
| `find_conflict_sources.py` | Traces each duplicate to its source `.xlsm` file; flags cross-bucket conflicts |
| `conflict_sources_to_excel.py` | Converts conflict JSON to two-tab Excel report |

---

## LLM Configuration

**LLM provider:** Configurable via `config/agent_llm_config.py` and resolved by `llm/llm_client.py` → `make_llm()`

**Supported options** (selected via `.env` and code-level provider choice):
- OpenAI GPT models
- Gemini models
- LM Studio local model (qwen2.5-coder-14b)

LangChain used in `find_mapping.py` for prompt templating and structured output (`with_structured_output(AISuggestedMapping)`).

---

## Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Block detection approach | Flat row-by-row | Hierarchical nesting was fragile across 3 formats; flat + `section_context` is sufficient |
| Hierarchy for LLM | Not needed | `section_context` (nearest header) gives enough signal |
| Headers/subtotals in rulebook | Excluded | `__LIKELY_HEADER__` / `__LIKELY_SUBTOTAL__` entries conflicted with real categories |
| Fuzzy matching | Not implemented | LLM fallback handles variants; exact match keeps false-positives at zero |
| Subtotal values in detect_blocks | Captured | NOI verification needs vendor-reported NOI subtotal for comparison |
| Rulebook v2 conflict resolution | Override > Auto > Majority vote | Human overrides are authoritative; auto mappings are algorithmic guesses |
| Rulebook v2 output location | `output_docs/` only | Never auto-write to `db/`; runtime stages read the current build artifact |
| AI prompt — category constraint | Must pick from existing list | Prevents LLM from inventing categories that silently miss classification |
| NOI tolerance | `max($1.00, 0.1% of actual)` | Absorbs rounding without masking real mapping errors |
| Capex excluded from NOI | SKIP bucket | Capex rows appear below the NOI line in T12 files |
| Folder structure | Numbered pipeline folders | Order is visible from directory listing; no ambiguity about sequence |
| Export / analysis scripts | Separate `utils/` and `analysis/` folders | Not part of the run-every-file pipeline; separating avoids confusion |
| Runtime rulebook selection | `config/rulebook_runtime.py` | Change the active profile in one place instead of comment/uncommenting multiple stage files |
| Agent LLM selection | `config/agent_llm_config.py` | Keep provider/model choice centralized per agent |
