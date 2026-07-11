# Naive / heuristic code inventory

A running note of the **deterministic, biased, or hand-tuned** bits in the new
parsing pipeline (`src/analysis/workflow/t12_workflow.ipynb`) — the opposite of the
AI-driven parts. The goal is to keep pushing these toward "AI proposes, arithmetic
verifies" and to know where the pipeline is still guessing.

Severity = how likely it is to misfire on an unseen format.

| Layer | Naive bit | Severity | Notes / mitigation |
|---|---|---|---|
| **Structure map — 8a `derive_layout`** | `value_columns` = "any column with numbers in ≥5 rows"; `description_columns` = "text left of the values" | ~~High~~ **removed** | This grabbed the `Variance` column on Chateau and index columns on Grande Reserve. **Deleted** — the AI map is now trusted directly. |
| **Structure map — 8c `reconcile`** | overrode the AI on `value_columns` / `month_header_row` / `data_start_row` (the "counting" fields) | ~~High~~ **removed** | The bias leaked *because* we prioritized this over the AI's correct read. **Deleted.** |
| **Module 9 `CODE_PREFIX_RE`** | regex of known code styles (dot/colon/mri/5-digit/dash) used to strip embedded codes | Low | **Degrades gracefully** — a brand-new code style just leaves the code in the description text; nothing breaks. |
| **Module 4 format detection** | known-format signatures (`PURE_CODE`, `FOREIGN_CODES`), `scan_rows=60`, `NCOLS=6`, `DECISION_THRESHOLD=0.15` | Low-stakes | It only *routes* known-vs-unknown; anything unfamiliar falls to "unknown" → the AI route. |
| **Modules 5–7 known extractors** | per-format hardcoded columns (`CODE_COL/DESC_COL=1,2`, `EMB_DESC_COL=1`, …), `detect_value_columns(min_hits=5)`, `TOTAL_KEYWORDS` | Medium | Format-specific, but only for the **3 known** formats; the AI route already handles any layout. |
| **Module 10 classifier** | `TOTAL_KEYWORDS` / `METRIC_KEYWORDS` keyword lists + per-class **signal sets** (`CLASS_SIGNALS`) | Low-Med | Hand-tuned weights **removed**. Now an unbiased **normalised signal-match**: each signal counts 1, a class's score = fraction of its signals satisfied (`satisfied / total`), argmax wins — so classes with different signal counts compare fairly (3/3 beats 3/8). Contra-indicators are positive signals (`not_subtotal_marked`). The only remaining bias is *which* signals define each class, and that is config (`CLASS_SIGNALS` / `SIGNAL_FUNCS` dicts, meant to move to a config file). The AI subsection anchors are **no longer scored** here — kept as facts for a future override layer. Cushioned by the NOI gate + feedback loop. |
| **Module 11 boundaries** | `GRAND_INCOME/EXPENSE/NOI_MARKERS` keyword lists | Low | Only the *cross-check* branch; the AI provides the independent one. |
| Pre-flight, `MAX_SCAN_ROWS/COLS`, `arithmetic_sum_of_above` | filename regexes / scan caps / pure arithmetic | None | Guards and math, not format bias. |

## Direction

- **Structure map**: now fully AI-driven + arithmetic-verified (naive code removed).
- **Classifier (Module 10)**: hand-tuned weights **replaced** by an unbiased, config-driven normalised signal-match. The remaining lever is the per-class signal lists in `CLASS_SIGNALS` — add a signal by naming it in a class list (+ its evaluator in `SIGNAL_FUNCS`); both are meant to externalise to a config file. Next steps if we want to trust the AI further: (a) the **verified-fact override layer** (arithmetic-validated subtotals / boundaries assign their class directly, after scoring); (b) **full-AI per-row classification** (Rung 3), still reconciled by the NOI gate.
- **Format detection**: a heuristic router; low priority since it degrades to the AI route.
