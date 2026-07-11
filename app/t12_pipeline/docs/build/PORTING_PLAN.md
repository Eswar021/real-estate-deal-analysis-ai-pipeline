# Porting the anchor-first workflow from the notebook into `src`

**Goal.** The anchor-first flow is proven in the notebook
(`src/analysis/workflow/t12_workflow.ipynb`) — known 3/3, unknown 7/7. This plan
turns that prototype into production `src` modules, swaps `pipeline_bridge.py` to
use them, and updates the Django UI. The bridge facade already isolates the UI, so
UI churn is contained.

**What we have vs. what's missing**
- Have: the full algorithm (format detect → column resolve → dynamic extract →
  anchor lock → classify + fact override → section → NOI → diagnosis/loop),
  `anchor_keywords.json`, and a clean bridge seam.
- Missing: proper `src` modules (notebook uses ad-hoc paths / `sys.path` / direct
  `make_llm`), the **confidence gate** and the **Stage-1 anchor gate UI**, and the
  new stage-file contracts.

---

## 1. New `pipeline/parsing/` package — notebook → module map

Put the ported code in a **new** `src/t12_pipeline/pipeline/parsing/` subpackage
(don't clobber the old `detection/` until the bridge is switched over).

| Notebook cell / functions | → `src` module |
| --- | --- |
| M3: `extract_cell_grid`, `gcell`, `gvalue`, `grid_row_map`, `load_cell_grid` | `parsing/cell_grid.py` |
| M4: `detect_format` (+ signatures/thresholds) | `parsing/format_detect.py` |
| M5–7: `has_total_keyword`, `total_keyword_hit`, `_apply_arithmetic`, `detect_value_columns`, `CODE_COL/DESC_COL/EMB_DESC_COL/NOCODE_DESC_COL` | `parsing/signals.py` (+ reuse `detection/keywords.py`) |
| M8a: `run_structure_agent`, `StructureMap`, `render_grid_for_agent`, prompt | `parsing/structure_agent.py` |
| M8b: `build_final_map`, `validate_subsections`; `build_known_map`, `_detect_known_layout` | `parsing/structure_map.py` |
| M9: `extract_row_signals_dynamic` | `parsing/extract.py` |
| M9b: `lock_anchors`, `nominate_anchors`, `_expense_units`, `_triple_holds`, derive, `apply_anchor_overrides` | `parsing/anchor_lock.py` |
| M10: `CLASS_SIGNALS`, `SIGNAL_FUNCS`, `classify_rows`, `reconcile_leaf_data`, `explain_scores` | `parsing/classify.py` |
| M11: `assign_sections` | `parsing/sections.py` (or fold into `classify.py`) |
| M12: `verify_noi` | `parsing/noi.py` |
| M13: `run_diagnosis_agent`, schemas, prompt | `parsing/diagnosis.py` |
| M14: `run_feedback_loop`, `apply_corrections` | `parsing/feedback.py` |
| Orchestrator `run_pipeline` | `parsing/run_parse.py` (the stage runner) |
| `anchor_keywords.json` | `config/anchor_keywords.json` (loaded via `config.paths`) |

**Conventions to enforce while porting** (src `CLAUDE.md`): no `sys.path`; all paths
via `config.paths`; all model selection via `config.agent_llm_config` (not direct
`make_llm(provider=...)`); fail-hard on missing files/schema; small functions.

---

## 2. Stage-file contracts (per upload)

Mirror the notebook's `workflow_output/<file>/NN_*.json` as the per-run outputs the
bridge reads/writes. New contract replaces the old detection files:

| New stage file | Replaces (old) |
| --- | --- |
| `03_cell_grid.json` | — |
| `04_format.json` | — |
| `10_final_map.json` (AI or template map) | — |
| `10b_anchor_lock.json` (status, candidates, evidence, locked) | — |
| `12_classified.json` (class + section + confidence per row) | `annotated_blocks.json` |
| `14_noi.json` (per-month + total) | `noi_comparison.json` |
| `15_diagnosis.json` / `16_feedback.json` | — |

Wire these into the manifest/paths so stages read from `MANIFEST_PATH`, like the
existing pipeline (no date-stamped path recomputation).

---

## 3. Bridge diff (`pipeline_bridge.py`) — keep the public API stable

Only one UI file imports the pipeline (the bridge), so the UI barely changes.

- `run_detection(upload, xlsx)` → **guts swapped**: calls `parsing.run_parse`
  through column-resolve + extract + **anchor lock**. Returns anchor status +
  (on GATE) candidates + arithmetic evidence + raw grid for the gate screen.
- **NEW `confirm_anchors(upload, {R,E,N})`** → re-check `R−E=N`, store locked
  anchors, optionally promote a novel phrasing into `anchor_keywords.json`.
- `apply_and_recompute(upload, fixes)` → generalize to **reclassify** flagged rows
  and re-verify NOI (same signature the `noi_verification` view already calls).
- `load_annotated_blocks` / `load_comparison` / `load_actual_noi` → point at the
  new stage files; add `confidence` + `section` per row.
- `run_mapping` / `load_mapped` / `save_mapped` / `load_categories` → **unchanged**
  (Stage 3 is the existing rulebook + AI-residue mapping).

---

## 4. UI changes (contained to the pages)

- **New Stage-1 anchor gate page** — only shown on `GATE`/`DERIVED`: renders the
  raw grid, highlights candidate R/E/NOI rows with each one's `R−E=N` verdict,
  click-any-row override, live re-verify → `bridge.confirm_anchors`.
- **`noi_verification` page** — adapt to the classification-based data (per-row
  class/section/confidence) and surface **low-confidence rows** for review.
- **`data_review` page** (Stage 3 mapping) — unchanged.

---

## 5. The two gates to build

- **Confidence gate** — in `classify.py`, compute each row's **margin** (top score −
  runner-up), threshold it, and emit `low_confidence_rows`. NOI is a net check, so
  this catches compensating errors it hides.
- **Stage-1 anchor gate** — the `confirm_anchors` bridge fn + the new UI page above.

---

## 6. Suggested order

1. **Port `parsing/`** modules (§1); unit-test against the 7 unknown + 3 known files
   (reuse the notebook's harness expectations: known 3/3, unknown 7/7).
2. **Config + stage files** (§2): move `anchor_keywords.json` into `config/`, define
   the stage-file contract in the manifest.
3. **Swap the bridge** (§3) + add `confirm_anchors`; keep public signatures stable.
4. **Build the two gates** (§5).
5. **UI** (§4): new anchor gate page + `noi_verification` data-shape update.

Each step is independently testable; the UI is touched last and least.
