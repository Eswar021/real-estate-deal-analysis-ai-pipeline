# T12 Pipeline — Claude Instructions

Real estate T12 financial statement pipeline for Oakdale Capital. Reads a raw Excel
T12, locks the revenue / expense / NOI anchors by arithmetic, classifies every row,
verifies the computed NOI against the vendor's, and maps each line item to a canonical
category.

Packaged as an installable package (`t12_pipeline`) — `pip install -e ./app/t12_pipeline`.
No `sys.path` manipulation anywhere.

> **⚠ The live pipeline is `pipeline/parsing/` + `pipeline/mapping/`, driven by the Django
> UI through `app/ui/t12_mapping/pipeline_bridge.py`.** The old batch runner
> (`run_pipeline.py`, `manifest/`, `detection/`, `mapping/run_stage.py`, `utils/`,
> `runner_utils.py`) and its `output_docs/` + `current_manifest.json` machinery are **DEAD
> CODE** — nothing in the UI or `parsing/` imports them. They are scheduled for deletion
> (W2 in `docs/build/PLANNED_ENHANCEMENTS.md`). Do not extend them; do not follow the
> manifest pattern for new work.

---

## How to Run

```bash
# One-time setup (editable install — picks up source changes automatically)
pip install -e ./app/t12_pipeline

# Secrets: ONE key runs all three agents. app/.env is gitignored — never commit it.
cp app/.env.example app/.env      # then fill in CLAUDE_API_KEY

# The app (this is the real entry point)
cd app/ui && python manage.py runserver

# Parse one file end-to-end from the CLI (Stage 1 + Stage 2, no UI)
python -c "from t12_pipeline.pipeline.parsing.run_parse import parse_file; \
           r = parse_file('<path>.xlsx'); print(r['anchor_lock']['status'], r['noi']['overall_pass'])"

# Build the rulebook (run when new reviewed .xlsm files arrive)
python -m t12_pipeline.build_rulebook.run
```

**Logs** — the pipeline owns its own logging (`config/logging.json` → `app/logs/t12.log`,
file-only, rotating). `profile` is ONE switch in that file, not a per-profile block:
- `summary` (default) — stage banners + the anchor / classification / NOI tables.
- `verbose` — adds the **per-row scoring table** (every row vs all 7 classes, `[x]` = the class
  assigned), per-row signals, the anchor-rows table, and the exact LLM input/output per call.

To switch: edit `"profile"` in `config/logging.json`. For a one-off run use the env override
`T12_LOG_PROFILE=verbose python manage.py runserver` (also `T12_LOG_FILE`, `T12_LOG_LEVEL`).
**Never put `T12_LOG_PROFILE` in `app/.env`** — env is read first, so it silently shadows
`logging.json` and makes editing `profile` there do nothing.

---

## Architecture (the LIVE path)

```
app/t12_pipeline/src/t12_pipeline/
├── config/
│   ├── paths.py             <- all paths (single source of truth) + LOG_DIR
│   ├── known_formats.json   <- per-format column layout; value_columns are CONFIG
│   ├── anchor_keywords.json <- anchor markers (a RANKER, never a gate)
│   ├── logging.json         <- log profile + file
│   ├── log_config.py        <- configure_logging(); the pipeline owns its file logging
│   └── agent_llm_config.py  <- model/provider per agent; ALL 3 on Anthropic + CLAUDE_API_KEY
│                               (mapping=sonnet-5, structure/diagnosis=opus-4-8)
├── llm/llm_client.py        <- make_llm(); logs LLM input/output at the 'verbose' profile
└── pipeline/
    ├── parsing/             <- THE live parse pipeline (Stage 1 + Stage 2)
    │   ├── cell_grid.py        Layer 1: read the workbook ONCE -> cell_grid
    │   ├── format_detect.py    known (3 formats) vs unknown
    │   ├── structure_map.py    build_known_map (config) | detect_structure_deterministic
    │   │                       | AI structure agent (FALLBACK only)
    │   ├── structure_agent.py  AI: columns + proposed anchors + subsections
    │   ├── extract.py          anchor_rows (Stage 1) + the full signal vector (Stage 2)
    │   ├── signals.py          signal primitives + value-block detection + arithmetic
    │   ├── anchor_lock.py      ARITHMETIC-FIRST R-|E|=NOI hash-join; keywords only RANK
    │   ├── classify.py         7-class scoring + fact override + subsection derivation
    │   ├── sections.py         revenue / expense / capex assignment
    │   ├── noi.py              verify_noi: bottom-up sums vs the locked anchors
    │   ├── diagnosis.py        AI: names mislabeled rows (only when NOI fails)
    │   ├── feedback.py         diagnose -> apply_fix -> re-verify (arithmetic-gated)
    │   ├── parse_log.py        ALL log rendering (banners + tables), profile-aware
    │   ├── stages.py           STEPS registry + the composite stages
    │   ├── run_parse.py        CLI/test one-shot runner
    │   └── legacy_adapter.py   to_annotated: classified rows -> the mapping stage's shape
    └── mapping/              <- Stage 3
        ├── map_blocks.py       rulebook lookup (certain -> contextual -> no_conflict -> unresolved)
        └── find_mapping.py     AI fallback for whatever the rulebook missed

data/input_T12_docs/<format>/   raw .xlsx test corpus, organised by detected format
db/rulebooks/                   versioned rulebook snapshots (written by build_rulebook)
app/logs/t12.log                the pipeline's rotating log (file-only)
```

**DEAD (W2, pending deletion):** `manifest/`, `detection/`, `run_pipeline.py`,
`mapping/run_stage.py`, `utils/`, `runner_utils.py`, and the `output_docs/` +
`current_manifest.json` flow they depend on. Nothing live imports them.

---

## The workflow (one run-state, not files)

ONE `state.json` per upload (+ `cell_grid.json` as a heavy side artifact), enriched by each
step. Every module exposes `run(state) -> state`; `stages.STEPS` is the name->step registry
that `pipeline_bridge.run_step` dispatches on, and the views are just the router.

```
Stage 0  preflight       screen_name -> screen_structure (reject rent rolls / model T12s)
Stage 1  extract_grid -> detect_format -> resolve_columns -> extract_anchor_rows -> lock_anchors
           known   -> build_known_map (known_formats.json)
           unknown -> detect_structure_deterministic; the ANCHOR LOCK is the oracle
                      (it reconciles => the columns were right); AI agent only if it can't
🛑 ANCHOR GATE           every file stops here; the user confirms R / E / NOI
Stage 2  apply anchors -> extract_signals -> classify -> sections -> verify_noi
           -> [NOI FAIL -> diagnose -> apply_fix -> re-verify, loop max 3] -> flag_low_confidence
🛑 CLASSIFICATION REVIEW  every file stops here
           user edits a row's class -> stage2_reverify: apply_edits -> verify_noi -> flag
           (re-enters the SAME noi node; never re-classifies, never calls the AI)
Stage 3  map_blocks (rulebook) -> find_mapping (AI fallback) -> data_review
```

**Every fork belongs to the FLOW** — decided by the data or the arithmetic, never by a caller
flag. (`run_feedback` once let a caller switch the diagnosis off, which silently discarded its
corrections; it was deleted. A caller may only re-enter a step, never disable part of one.)

---

## Key invariants (do not break these)

- **The AI proposes, the arithmetic decides.** The anchor lock is `R - |E| = NOI` over ALL
  value-bearing rows (hash-join on the annual total); keywords only RANK the reconciling
  triples, they never gate which rows qualify. The diagnosis loop applies the AI's
  reclassifications and keeps them ONLY if NOI then reconciles. Locked anchors are never
  reclassified, so the AI cannot move the target.
- **Tolerances are flat dollars, never percentages.** Vendors export whole-dollar integers
  (our reader keeps full precision), so the only real error is their rounding: anchor lock
  **$1**, subsection **$1**, NOI verify **$10**. A percentage scales with the value ($10k on a
  $2M total) and would hide a real misclassification.
- **Known-format config supplies the column layout ONLY.** `value_columns` are constant within
  a format (configured); `month_header_row` / `data_start_row` genuinely vary file-to-file and
  are detected.
- **`cell_grid` is the single source of truth** — the workbook is read exactly once; every
  later step reads the grid.
- **Row classes:** METADATA · SECTION_HEADER · SUBSECTION_HEADER · DATA · SUBSECTION_SUBTOTAL ·
  SECTION_SUBTOTAL · COMPUTED_METRIC. `verify_noi` sums only DATA rows by section (capex
  excluded).
- **The money is verified ONCE, at Stage 2.** `verify_noi` is the only place NOI is computed, and
  `noi.NOI_TOLERANCE` is the only definition of "reconciles". Downstream pages *display*
  `classification.noi` — they never re-derive it. (data_review did, and drifted: it summed
  `rev − exp` vs the pipeline's `rev − |exp|`, so a negative-expense vendor showed a $730k
  difference on a file Stage 2 had passed.) Mapping assigns categories; it cannot move money.
- **A re-entry never re-runs the step it re-enters.** `stage2_reverify` / `stage3_update_mapping`
  apply the user's edit onto the reviewed result and re-verify; re-running `classify` / the
  mapping would recompute over the edit and discard it (the old Recompute bug). Each row carries
  `source` ∈ auto/ai/manual — display only, no behaviour hangs off it.

---

## Rulebook shape (Stage 3)

```json
{ "certain": {}, "contextual": {}, "no_conflict": {}, "unresolved": {} }
```

Lookup order in `map_blocks`: certain -> contextual -> no_conflict -> unresolved (-> AI).

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
- **Only `cell_grid.extract_cell_grid` opens the .xlsx.** Every other step reads `cell_grid`.
- **No caller flags that disable part of the workflow.** A caller re-enters a step; the flow owns
  its forks. (Tests mock the AI agents — `run_structure_agent` / `run_diagnosis_agent` — rather
  than switching the graph off.)
- **No `sys.path` manipulation.** The package is installed via `pip install -e`; use real imports.

---

## What Not To Do

- **Extend the dead batch pipeline** (`manifest/`, `detection/`, `run_pipeline.py`,
  `mapping/run_stage.py`, `utils/`) or follow its manifest/`output_docs` pattern — it's pending
  deletion (W2). New work goes in `parsing/` + `mapping/` behind the run-state.
- Import from `archive/` or the old analysis notebooks
- Reintroduce multiple active rulebook versions into the runtime path
- Make pipeline stages write to `db/` (only `t12_pipeline.build_rulebook` does)
- Reopen the raw Excel anywhere except `cell_grid`
- Add `except: pass` or silent error swallowing
- **Let keywords GATE the anchor lock** — they rank the arithmetic's results, nothing more
- **Use a percentage tolerance** anywhere in the R−E=NOI family (see Key invariants)
- Add `sys.path.append(...)` blocks back into modules
- Add backwards-compatibility shims for removed code — just delete it cleanly
- Hardcode paths — always use `t12_pipeline.config.paths`
