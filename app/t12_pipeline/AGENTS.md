# T12 Pipeline — Codex Instructions

This file is for work under `app/t12_pipeline/`.
Follow everything here before generating code for this pipeline.

## Read First

Before planning or changing any stage:

1. Read `docs/README.md`

If you need older chat context, use these as reference only:

- `archive/references/codex_chats.txt`
- `archive/mapping_rulebook_docs/`

Do not treat archived notes as the active source of truth.

---

## Project Architecture

Packaged as a proper Python package. Install once: `pip install -e ./app/t12_pipeline`.
All entry points are `python -m`. No `sys.path` manipulation anywhere.

```text
app/t12_pipeline/
├── pyproject.toml              ← declares the t12_pipeline package
├── src/
│   ├── t12_pipeline/           ← installable package root
│   │   ├── build_rulebook/     ← one-time tool, NOT part of the per-file pipeline
│   │   │   ├── run.py          ← entry: python -m t12_pipeline.build_rulebook.run
│   │   │   ├── build_rulebook.py
│   │   │   ├── build_client_review_rules.py
│   │   │   ├── extract_reviewed_row_history.py
│   │   │   └── build_historical_rule_support.py
│   │   ├── config/
│   │   │   ├── paths.py
│   │   │   ├── rulebook_runtime.py
│   │   │   ├── rulebook_utils.py
│   │   │   └── agent_llm_config.py
│   │   ├── llm/
│   │   │   └── llm_client.py
│   │   ├── pipeline/
│   │   │   ├── manifest/       ← Stage 0: writes current_manifest.json
│   │   │   │   └── runner.py
│   │   │   ├── detection/      ← Stage 1: detect → annotate → compute NOI → compare NOI
│   │   │   │   ├── detect_blocks.py
│   │   │   │   ├── annotate_totals.py
│   │   │   │   ├── compute_noi.py
│   │   │   │   ├── compare_noi.py
│   │   │   │   ├── corrections.py
│   │   │   │   └── run_stage.py
│   │   │   ├── mapping/        ← Stage 2: auto-map → AI fallback
│   │   │   │   ├── map_blocks.py
│   │   │   │   ├── find_mapping.py
│   │   │   │   └── run_stage.py
│   │   │   ├── utils/
│   │   │   ├── runner_utils.py ← run_python_module(): `python -m` subprocess wrapper
│   │   │   └── run_pipeline.py ← master stage runner
│   │   └── __init__.py
│   └── analysis/               ← diagnostic notebooks, NOT in the package
├── data/
├── db/
│   └── rulebooks/              ← versioned rulebooks written by t12_pipeline.build_rulebook
├── output_docs/
│   ├── current_manifest.json   ← always-latest pointer, overwritten each Stage 0 run
│   └── <timestamp>/            ← per-run output dir
│       ├── run_manifest.json   ← frozen snapshot for this run
│       ├── 1_detection/        ← output folders keep stage numbers (semantic, not Python import paths)
│       │   ├── block_detection/
│       │   ├── annotated_blocks/
│       │   └── noi_verification/
│       └── 2_mapping/
│           ├── auto_mapped/
│           └── ai_mapped/
└── docs/
```

Source folders (`detection/`, `mapping/`, `manifest/`) dropped their digit
prefix because Python identifiers can't start with a digit. The stage
numbers (0, 1, 2) still appear in `STAGE_MODULES` (run_pipeline.py),
in `output_docs/<ts>/` subfolders, and in conversation.

The active pipeline is:

```text
Stage 0: write run manifest (picks latest rulebook from db/rulebooks/)
Stage 1: detect rows → annotate totals → compute NOI → compare NOI
Stage 2: auto-map rows → AI fallback for unmapped rows
```

`src/build_rulebook/` is a separate tool — run it manually when new .xlsm files arrive.
It writes to `db/rulebooks/mapping_rulebook_<timestamp>.json`.
The pipeline does not run it; Stage 0 (manifest) just picks the latest file from that dir.

---

## Active Pipeline Flow

### Stage 0 — Manifest

`src/pipeline/0_manifest/runner.py`

1. Scans `db/rulebooks/` for the latest `mapping_rulebook_*.json`
2. Loads and embeds the full rulebook in the manifest
3. Reads AI config from `config/agent_llm_config.py`
4. Collects input file list from `data/input_T12_docs/`
5. Computes all output paths (using paths.py constants)
6. Writes:
   - `output_docs/<timestamp>/run_manifest.json` (frozen per-run snapshot)
   - `output_docs/current_manifest.json` (always-latest pointer)
7. Creates all output directories

Fails hard if `db/rulebooks/` is empty.

### Stage 1 — Detection + NOI Verification

Sub-step order in `run_stage.py`:

1. `detect_blocks.py`    → `block_detection_dir/`
2. `annotate_totals.py`  → `annotated_blocks_dir/`  (adds is_total_revenue/expense/noi flags)
3. `compute_noi.py`      → `actual_noi_dir/` + `computed_noi_dir/`
4. `compare_noi.py`      → `noi_comparison_dir/`

Important:

- `detect_blocks.py` is the only Stage 1 script that reads raw `.xlsx` files
- After block detection, all downstream steps work from JSON artifacts only
- `compute_noi.py` uses `statement_side` directly — no mapping required
- All paths come from `manifest["l1"]["paths"]`

### Stage 2 — Mapping

Sub-step order in `run_stage.py`:

1. `map_blocks.py`   → `auto_mapped_dir/`  (reads from annotated_blocks_dir)
2. `find_mapping.py` → `ai_mapped_dir/`   (AI fallback for unmapped rows)

Important:

- Reads input from `manifest["l1"]["paths"]["annotated_blocks_dir"]` (Stage 1 output)
- `map_blocks.py` receives the rulebook dict directly from the manifest (no file load)
- `find_mapping.py` receives `rulebook` and `ai_mapping_logs_dir` as parameters
- AI config comes from `manifest["l2"]["ai"]`
- All output paths from `manifest["l2"]["paths"]`

---

## Golden Rules

### Manifest Is the Config Source for Stages 1+2

- Stages 1 and 2 read all paths and config from `output_docs/current_manifest.json`
- Do not reintroduce `config/paths.py` date-stamped path imports in stage runners
- `MANIFEST_PATH` (from paths.py) is the only thing stages 1+2 import from config

### `db/rulebooks/` Is Written by build_rulebook Only

- The pipeline (stages 0-2) never writes to `db/`
- `src/build_rulebook/` writes to `db/rulebooks/` — that's its sole output
- Stage 0 reads from `db/rulebooks/` (picks latest file)

### One Current Rulebook Only

- The active runtime path uses one current rulebook only
- Do not reintroduce live `v1 / v2 / v3` switching into the active pipeline

### No Silent Guessing In Core Logic

- If the current rulebook can map a row, map it
- If it cannot, leave the row unresolved and let the AI stage handle it
- Do not add hidden keyword fallbacks, broad fuzzy logic, or best-effort guesses

### Keep Contracts Stable

- Preserve the existing Stage 1 JSON contract
- Adding non-breaking metadata (like the `is_total_*` flags) is okay
- Do not casually rename or remove keys used by later stages

### Numbered Stages Stay

Keep these folders and stage numbers:

- `0_manifest`
- `1_detection`
- `2_mapping`

---

## Coding Philosophy

### Keep It Visible

- Small functions
- One logical unit per function
- Direct execution paths
- No deep abstraction chains

### Fail Hard

Do not silently continue when assumptions break:

- Missing expected input file → stop
- Missing manifest → stop with clear message
- Broken schema assumption → stop

### No Premature Frameworks

- Prefer thin runners over architectural rewrites
- Prefer explicit code over generic dispatch

---

## Config Rules

Use these files as the only active config sources:

- `config/paths.py` → all paths (used by manifest runner to compute values; stages 1+2 read from manifest)
- `config/rulebook_runtime.py` → build_rulebook script list + output path
- `config/agent_llm_config.py` → agent → provider/model selection

Do not hardcode file-system paths in stage logic.
Do not scatter model selection across multiple files.

---

## Stage 1 Output Contract

Top-level fields must remain:

- `file`, `file_path`, `format`, `data_start_row`, `column_headers`, `summary`, `rows`

For row entries, the important fields are:

- `row`, `type`, `description`, `section_context`, `section_path`, `values`
- `statement_side` — `"revenue"` / `"expense"` / `"capex"`
- `is_total_revenue`, `is_total_expense`, `is_noi` — booleans, set by annotate_totals
- `mapping`, `not_found`, `mapping_source`
- `ai_suggested_mapping`, `ai_confidence`, `ai_reasoning` — added by find_mapping

Non-breaking metadata:

- `inferred_statement_side`, `statement_side_source`, `client_review_note`
- `unresolved_reason_type`, `historical_candidate_mappings`
- `historical_statement_sides`, `historical_section_paths`

---

## AI Mapping Rules

`find_mapping.py` is the AI fallback stage.

Rules:

- Runs only on rows where `not_found` is `true` and `statement_side != "capex"`
- Must choose from the current canonical categories only
- Must use the rulebook embedded in the manifest, not any archived snapshot
- Must consume Stage 1 JSON context, not re-parse the source Excel

Preserve prompt/response logging under:

```text
output_docs/<timestamp>/2_mapping/ai_mapping_logs/
```

---

## Script Docstring Standard

Every stage runner or major executable script should have a module docstring that states:

- What it does
- What it reads
- What it writes
- Whether it calls an LLM
- How to run it

Keep docstrings factual and short.

---

## What Not To Do

- Import from `archive/`
- Reintroduce multiple active rulebook versions
- Write Stage 0-2 outputs into `db/`
- Make downstream mapping stages reopen raw Excel files
- Add `except: pass`
- Add hidden keyword heuristics in Stage 1 without being asked
- Hardcode paths in stage runners (read from manifest instead)
- Reintroduce digit-prefixed source-folder names (`0_manifest`, `1_detection`, `2_mapping`) — Python can't import them
- Add `sys.path.append(...)` blocks back into modules — the package is pip-installed
- Change stage numbering or folder names beyond the existing convention
