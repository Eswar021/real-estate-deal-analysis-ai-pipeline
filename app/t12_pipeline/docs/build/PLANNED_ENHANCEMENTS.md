# Planned Enhancements — T12 pipeline

The core pipeline (Stage 0 preflight → anchor gate → classification review → mapping →
data_review) and the full restructure (one run-state, `run(state)` steps, thin bridge, views
as router) are **done**. This is the running list of forward-looking improvements + their
designs, so we keep track of what's decided and why.

Status legend: 💡 idea/decided · 🔨 to build · ✅ done

---

## 1. ✅ Arithmetic-first anchor detection — DONE

**Built** in `parsing/anchor_lock.lock_anchors` (arithmetic-first rewrite; keyword-first
retired). Verified **byte-identical** output (status / anchors / passing / candidates) on all 7
sample files, and a synthetic novel-wording + negative-expense file now locks (status `DERIVED`)
where keyword-first returned `NONE`. Wired unchanged through the bridge — gate re-verify /
confirm / classify / NOI all green. **What changed vs. the design below:** kept the keyword
split-pair list as the bounded pair set (a full all-pairs search invents phantom sums); the
gate's `passing` list is trimmed to the *contenders* (winner + triples that tie it on
keyword-confirmation + revenue magnitude) so coincidental sub-arithmetic triples don't spam it;
`DERIVED` now means "one clear triple, but its NOI row carried no NOI keyword" (found purely by
the math). Design as built:

**Was:** keywords *nominate* a small candidate shortlist for R/E/NOI, then the `R − E = NOI`
arithmetic picks the real triple. Keywords were a **gate** — a novel vendor term that isn't in
`anchor_keywords.json` never got nominated, so that anchor couldn't lock.

**Now:** the **math finds the triples first** over *all* value-bearing rows (hash-join on the
annual total), then keywords + position only **rank** the (few) triples that reconcile. Keywords
are a tie-breaker, not a gate → robust to unseen vendor wording.

### Algorithm (the "3SUM via hashing" / hash-join trick)

We never know which row is R/E/NOI up front — we hypothesise and let the arithmetic derive the
missing one:

```
candidates = rows with >= 6 numeric monthly values      # data + subtotal rows only
table      = { round(row.value_vector) -> row }          # hash rows by their monthly vector

for each ordered pair (a, b) with a above b:             # pretend a = Revenue, b = NOI
    needed_E[m] = a[m] - b[m]      for each month m       # the Expense this pair implies
    if table has a row E ~= needed_E (within tolerance) and a < E < b:
        record triple (R=a, E=E, N=b)

rank triples by: keyword match (R/E/NOI terms) + bottom-most + largest magnitude
  one  -> AUTO ; several -> GATE ; none -> split-pair pass / derive / NONE
```

- **Why it's fast:** fixing two of the three and *looking up* the third turns the naive
  `O(n³)` (200³ ≈ 8M triples, tens of seconds in Python) into `O(n²)` (≈ 40K pair-probes,
  milliseconds). This is the classic **3SUM-reduced-by-hashing** = a hash join.
- **Tolerance:** hash by the value-vector rounded to the nearest dollar; verify a probe with
  the real tolerance `max($1, 0.5%)`. (Vendor grand totals are usually exact, so rounding is
  safe; the % tolerance is just a float-noise guard.)
- **Sign convention:** compare against the expense **magnitude** (`a − |E| = b`) so
  negative-signed vendors reconcile (already fixed in the current lock).
- **Split-pair expenses** (E = "controllable" + "non-controllable"): the single-row lookup
  covers most files; add a second pass that also indexes plausible expense *pair-sums* (bounded
  — only rows that look like expense subtotals), or fall back to the keyword split-pair list.

**Effort:** rewrite of `anchor_lock.lock_anchors` (the nominate step becomes a ranker). The
`reconcile_triple` / sign / split logic already exists. Not a fix (current lock passes all 7
files) — a robustness upgrade for novel vendors.

---

## 2. ✅ Deterministic-first structure finder (AI as fallback) — DONE

**Built** in `structure_map.detect_structure_deterministic` + `structure_map.run` (routing) +
`signals.detect_value_block`. For unknown files we read the columns straight off the grid — value
cols = the LONGEST contiguous numeric run (trailing junk columns trimmed), description = every
column left of it minus bare account-code columns — then the **anchor lock is the oracle**: if
any triple reconciles, the columns were right and we skip the AI; only a NONE lock (or no value
block) falls back to `run_structure_agent`. Adds `state["structure_source"]` ∈ {known,
deterministic, ai}.

**Verified:** all 7 validated unknown-format sellers get anchors **identical to the AI baseline**
with **zero AI calls**; the AI fallback was validated live once (returns the same anchors, its
subsections make NOI pass). Across the full 24-file raw-seller corpus: 23/24 lock + pass NOI
deterministically (the 1 failure is the Mirador bug, below — a classification issue, not columns).

<details><summary>original design</summary>

**Was:** known formats use a deterministic template map (`build_known_map`); *unknown*
formats always go straight to the AI structure agent.

**Change:** for unknown files, **try deterministic column detection first**, run the anchor
lock, and only call the AI if it can't reconcile:

```
detect columns deterministically  (value cols = numeric density / first contiguous run [have];
                                    description col = leftmost text col; month-header + data-start rows)
run the arithmetic anchor lock (section 1)
    reconciles?  -> columns were right -> DONE, no AI.  We KNOW because the numbers add up.
    NONE?        -> deterministic detection failed -> call the AI structure agent, lock again.
```

- **This decides ONLY the columns + the 3 anchors.** Subsections are derived later
  (arithmetic, Stage 2); mappings are Stage 3 (rulebook + a different AI). So the AI structure
  agent's job shrinks to **column-layout detection for files the deterministic detector can't
  handle** (merged cells, description spread across columns, embedded second tables).
- **How we know a file "needs AI":** we don't pre-judge it — the **arithmetic lock is the
  oracle**. If deterministic columns produce a reconciling `R−E=NOI`, they were right; if not,
  fall back. (Risk of wrong-columns-that-reconcile-by-fluke is negligible — `R−E=NOI` across 13
  months is a very tight constraint.)
- **Note:** the user has tested unknown files and the AI passes the gates well, so this is a
  **cost/latency optimization** (fewer AI calls), not a correctness need. Do after the AI path
  is validated once with the key.

</details>

---

## 3. ✅ Subsection derivation false-positives — DONE (tolerance fix)

The subsection scan (`signals.apply_arithmetic` → `arithmetic_sum_of_above`) was mis-marking a
**revenue leaf** as a subtotal: Cardinal row 30 "Cable/Vendor Commissions" ($20,001) because the 3
unrelated lines above it summed to within $37 — *inside the old `max($1, 0.5%)` = $100 window*.
That phantom subtotal was then dropped from the revenue sum, so NOI failed (and the feedback loop
couldn't fix it — validated subtotals are locked). **Fix:** the subsection tolerance is now a
flat **$1** (no percentage). A real subtotal equals its members to the dollar; the % just scaled
the window with the value and let coincidences in. Across 24 files every real subtotal reconciles
≤$1, and the nearest uncorroborated coincidence is $19 — so $1 is safe with wide margin.

Still-valid future work (not blocking): **nested** subtotals (iterate: treat found leaf subtotals
as members, re-scan up) and **odd-ordered** ones (leave to the classifier's bold/"Total" signals —
don't brute-force subset-sum). Subsections aren't load-bearing (they only feed the "mark subtotal"
override), so this is polish.

---

## 3b. ✅ Reconciliation tolerances — all flat, no percentages

Every `R−E=NOI`-family check dropped its `0.5%` component for a flat dollar tolerance, sized to
the **vendor's own whole-dollar rounding** (our reader keeps full precision; vendors export
integers). Verified across all 24 raw-seller files:

| check | rows summed | max real drift | tolerance |
| ----- | ----------- | -------------- | --------- |
| anchor lock (`_amatch`) | 3 grand rows | $1 | **$1** |
| subsection (`apply_arithmetic`) | a few | ≤$1 (phantom at $19) | **$1** |
| NOI verify (`noi._match`) | ~130 leaves | $5 (Mesquite) | **$10** |
| AI subsection validate (`validate_subsections`) | member rows | — | **$10** |

Why flat beats %: on a $2M total, `0.5%` is a **$10,000** window that would silently pass a real
$3k misclassification. The flat $10 covers legitimate rounding (max observed $5) yet is 1000×
tighter, so real errors surface instead of hiding.

---

## 3c. 🐞 Mirador — diagnosed. Two causes + a fix batch (🔨 to build)

`Mirador Seller T12.xlsx` (embedded_code_in_a) was the only file of 24 to fail NOI ($6.4M off).
Fully diagnosed — anchors + columns are correct; two independent issues:

1. **Carry-forward double-count (revenue 2×).** Row 29 "Leased Rents" (6,452,283) is a *subtotal
   carried forward* — it equals rows 19+20+21 ("Total Gross Scheduled Rent") but sits as the
   opening line of the next block, with no "Total" keyword, not bold, and its members separated
   by a header (so `arithmetic_sum_of_above` can't reach them). Plus row 23 "Economic Occupancy
   Rate" (1,007) is a *rate*, not a dollar. `6,452,283 + 1,007 = 6,453,290` = the exact drift.
   → This is the hard "odd-ordered subtotal" case (§3); the **AI diagnosis loop already fixes it**
   (reclassifies 29→SUBSECTION_SUBTOTAL, 23→COMPUTED_METRIC). No deterministic change needed.
2. **Spurious column O.** `detect_value_columns` (known path) includes any column with ≥5 numeric
   cells. Mirador's col O has exactly **5 stray cents** (rows 22,38,62,65,115: −0.01, 10.51, …) so
   it was swept in as a 14th value column; being last + empty in the anchor rows, it made
   `overall_pass=None→False`. River Point has the *same* junk but only **4** cells → excluded.
   A one-cell threshold coincidence. Confirmed fix: trim O **and** the diagnosis reclassify → PASS.

**Root insight (verified across all known files):** value columns are **constant per format**
(`code_in_a_desc_in_b`=C–O, `embedded_code_in_a`=B–N, `no_code`=B–N); only `month_header_row` +
`data_start_row` vary. So the clean fix is **config**, not a threshold tweak.

### Fix batch — ✅ DONE
1. ✅ **`config/known_formats.json`** (lands W1). Per format: `description_columns`, `code_*`,
   **explicit `value_columns`**, and `month_header_row` / `data_start_row` = `"dynamic"` (they vary;
   the config *shape* still allows a literal like `[9,10]` for a future fixed-header format).
   `structure_map.build_known_map` reads it via `KNOWN_FORMAT_LAYOUTS` → col O can never sneak in
   (Mirador now B–N). Retired the hardcoded column constants + `detect_value_columns`. `paths.py`
   gets `KNOWN_FORMATS_PATH`.
2. ✅ **Month-label display** — `legacy_adapter.column_headers` now joins the whole header band per
   column (Mirador → "Month Ending 04/30/2026 Actual"; single-row files unchanged; date cells
   formatted "%b %Y").
3. ✅ **Diagnosis logging + file logging.** `feedback.run_feedback_loop` logs each iteration
   (verdict · proposed fixes · per-row reclassifications · fail-cols before→after) on `t12.diagnosis`.
   `settings.py` file logging is ON by default (rolling `logs/t12.log`, full DEBUG; `T12_LOG_FILE`
   override; console stays at `T12_LOG_LEVEL`).
4. ✅ **`max_iters` 5 → 3** via `feedback.DEFAULT_MAX_ITERS` (overridable through `state["max_iters"]`).
5. ✅ **No-progress early-exit** — the loop stops when a fix doesn't reduce the failing-column count
   (`noi_fail_cols_after >= before`) — arithmetic, not trusting the model to self-declare.

Result: **Mirador col O eliminated** (deterministic), and its double-count is fixed by the AI
diagnosis (which now *succeeds* — reclassify-only passes once col O is gone; verified by simulation).
Full corpus still 23/24 deterministic (Mirador the 1, resolved by the diagnosis loop in the UI),
original-7 anchors byte-identical. **Live-AI end-to-end confirmation: re-run Mirador in the UI.**

---

## 4. ✅ Pipeline logging — DONE (v2: profile-driven, owned by the pipeline)

**v2 (current):** logging moved OUT of the views and INTO the pipeline steps, so CLI/tests log
the same as the UI. `pipeline/parsing/parse_log.py` renders every stage (banner → steps → end
banner) with the anchor / classification+scoring / initial+final NOI tables + the diagnosis loop;
`config/log_config.py::configure_logging()` sets up ONE rotating **file-only** handler from
`config/logging.json` (called by `t12_mapping.apps.ready()` and `run_parse`). **Profiles**:
`summary` (default) = banners + tables; `verbose` = + per-row fired-signals, anchor-rows table,
full diagnosis reasons, and the exact LLM input/output (captured once in `llm_client` via a
callback). Override with `T12_LOG_PROFILE` / `T12_LOG_FILE` / `T12_LOG_LEVEL`. Retired the
view-level `debug_log.py` (which double-logged classify + printed to the terminal) and the bridge's
Stage-3 `print()`s. Log at `app/logs/t12.log`.

**v1 (superseded):** `app/ui/t12_mapping/debug_log.py` — per-page `t12.<page>` loggers wired into
the four views; the old `report.py` CLI dump was deleted then (its helper `reconcile_leaf_data` too).



Print the data at the **view** level (each view already receives the full run-state back from
the steps), so we see exactly which view ran + what it produced — but do it with Python
`logging`, not raw `print`:

- per-page loggers, e.g. `logging.getLogger("t12.anchor_gate")`.
- `logger.info("gate · AUTO · R68/E202/N203")` — always-on one-liner (flow visibility, low noise).
- `logger.debug(<full row table / state slice>)` — detailed dump, shown only at DEBUG level.
- configure in `settings.py`: console handler + optional **file** handler (per-run or rolling);
  level via env (`T12_LOG_LEVEL=DEBUG`).

Gives quiet-by-default, full-data-on-demand, kept-in-a-file, and per-view attribution.
The old `report.py` CLI dump has been removed (view-level logging replaces it).

**Effort:** small — a logging helper + a few `logger.info/debug` calls in the four views +
a `LOGGING` block in settings.

---

## 4b. 🐞 Stage-2 state overwrite — `run_feedback` is a leaky flag (🔨 to fix)

**Symptom (found in a real UI run of Mirador):** the gate's classify ran the AI diagnosis and fixed
the classification (log: `FIXED at iter 1`), but data_review then showed an NOI difference of
**6,453,290** — the original double-count. The saved state proved it:
`run_feedback=False · diagnosis=null · row 23=DATA · row 29=DATA · overall_pass=False`.

**Root cause:** `noi_verification/views.py` re-runs `classify` with **`run_feedback=False` on every
POST, before it checks the action** — so **Save & Continue re-classifies from scratch without the
AI and overwrites the corrected state**, then maps the wiped result. The log showed run #1 (the AI
working); the state held run #2 (the wipe). Same run_id, clobbered.

**The real flaw is architectural:** `run_feedback` is a **caller-controlled flag on a core workflow
step** (it exists only so tests/CLI can skip AI cost). Any caller can therefore silently disable
part of the workflow. The flow must own its own conditional edge instead (LangGraph-style):

```
classify → sections → verify_noi ──┬── pass ──→ flag → done
                                   └── fail ──→ diagnose → apply_fix → verify_noi ─┐
                                                    ▲                              │
                                                    └──── loop (max 3 / no-progress)┘
```
Callers just **re-enter the graph**; the graph decides whether the AI runs. (The "fix module" already
exists — `feedback.apply_corrections`, arithmetic-gated: the AI proposes, the math decides. And
`feedback.history` already records each iteration's rows/from→to/reason/fail-cols.)

### Flag audit — every caller-controlled input in the workflow
Grepped all `state.get(...)` inputs + the bridge signature. Only **one** is a real problem:

| input | where | verdict |
| ----- | ----- | ------- |
| **`run_feedback`** | `stages.classify` | ❌ **REMOVE** — lets a caller switch OFF a core workflow step (the cause of this bug). Not needed in production. |
| `max_iters` | `feedback.run` | ⚠ tuning knob passed through the state; no caller sets it. Make it **config-only** (`DEFAULT_MAX_ITERS`), not a state input. |
| `anchors` | `stages._apply_confirmed_anchors` | ✅ legit — real user data (the gate's picks), not a behaviour switch. |
| `save`, `with_grid` | `bridge.run_step` / `get_state` | ✅ legit — persistence/perf plumbing; they don't change any workflow decision. |

**Testing without flags:** either run the real graph with the AI agents **mocked** (as the current
scripts already mock `run_structure_agent`), or call individual `run(state)` steps with **fixture
state** from a `tests/` folder. Neither needs a production escape hatch.

### Branch map — who decides each fork
| stage | branch | decided by |
| ----- | ------ | ---------- |
| preflight | ok / reject (t12 · rent_roll · model · not_t12) | data |
| stage 1 | format known / unknown | data (detector score) |
| stage 1 | unknown → deterministic **vs** AI structure agent | **arithmetic** (trial anchor lock reconciles?) |
| stage 1 | lock AUTO / DERIVED / GATE / NONE | arithmetic + keyword rank |
| gate | confirm anchors | **user** (legit) |
| stage 2 | NOI pass → done · fail → diagnose | data — **but today gated by `run_feedback` (caller)** ❌ |
| stage 2 diag | DATA_PROBLEM / not-CLASSIFICATION_PROBLEM / no fixes → stop | AI verdict |
| stage 2 diag | NOI reconciles → FIXED · no progress → stop | **arithmetic** |
| stage 2 diag | max iterations | config |
| stage 3 | unmapped rows → AI mapping | data |

Every fork is already **flow-owned** except the one marked ❌ — so the LangGraph-style
"caller re-enters, graph decides" model is achievable by deleting a single flag.

### Fix batch — ✅ DONE
1. ✅ **`run_feedback` removed from the workflow** — NOI failing IS the trigger; the fork is the
   graph's: `verify_noi → [fail] → diagnose → apply_fix → re-verify` (arithmetic-gated). No caller
   can switch it off. `parse_file` dropped `run_feedback`/`max_iters`; tests mock
   `run_diagnosis_agent` exactly as they already mock `run_structure_agent`.
2. ✅ **NOI page: only `recompute` re-classifies** (user changed anchors → re-enter the graph).
   `continue` just maps — it no longer discards the reviewed/corrected classification.
3. ✅ **Corrected classification + final NOI now logged** after the diagnosis (you can watch
   DATA 113→108 · COMPUTED_METRIC 1→3 land, then `NOI verify (final): PASS`).
4. ✅ **`find_mapping` live prints → `t12.stage3` logging** (per-row AI mapping at DEBUG, the
   unmapped-count at INFO, rate-limit/errors at WARNING). Only the dead batch block still prints
   (goes away with W2).
5. ✅ **Fired signals shown in every profile** — the classification table carries `conf` (score) +
   `signals` (which raw signals fired), so a class is never an unexplained assertion.

**Verified with no LLM call** (diagnosis mocked with the rows the real AI proposed): Mirador
NOI FAIL → diagnose → apply_fix → re-verify → **PASS**, corrected classification persists.
Corpus 23/24, anchors byte-identical, Django clean. **Remaining: re-run Mirador in the UI**
end-to-end (gate → corrected classification → NOI PASS → mapping with no NOI difference).

---

## 4c. 📋 Client meeting 12-Jul — action items (transcript in `master_docs/client_sent_docs/12th_july_new_workflow_dicussions/`)

| # | item | status |
| - | ---- | ------ |
| 1 | **Keyword-based winner selection for ambiguous N-way matches** — when several triples reconcile, use keywords to pick/recommend a winner; user can override | ✅ **done** (§1: keywords RANK the reconciling triples; we return the winner + only genuine contenders) |
| 2 | **Unknown path: keyword matching before AI** (not AI-only) | ✅ **done** (§2: deterministic columns → arithmetic lock w/ keyword ranking → AI only as fallback) |
| 3 | **Reduce NOI diagnosis iterations to save credits** | ✅ **done** (max 3 + no-progress early-exit) |
| 4 | **Take the 3 hardcoded templates out of the code into an input file** | ✅ **done** (W1: `config/known_formats.json`) |
| 5 | **Anchor-keywords rulebook** — build a SECOND rulebook from the reviewed `.xlsm` (grand-total revenue/expense/NOI names), replacing the hand-made `anchor_keywords.json`. Shivam: keep it a **separate file** from the account-mapping rulebook so the two logic areas stay independent; `build_rulebook` emits both; the pipeline loads both. | 🔨 **TODO — his stated next step #1** |
| 6 | **Per-row class dropdowns on the Stage-2 review** so the user can correct a classification | ✅ **done** (§4d: `stage2_reverify` + dropdowns + `source` badges — no lock, no re-classify, no AI on edit) |
| 7 | **Remove the Recompute button; enforce stage-gated flow** — "once stage 1 is locked you can't go back; stages are go/no-go gates" | ✅ **done** — anchors are read-only on the NOI page; only the GATE can re-classify now |
| 8 | **Verify Stage 3 mapping uses the locked anchors** | ✅ **verified** — `to_annotated` reads R/E/NOI from `final_map` (= `structure_map` after the gate's picks) and sets `is_total_revenue/expense/noi` + `statement_side` from them |
| 9 | Template-inventory file (10 templates / vendor fingerprints across 25 files) as future template recognition | 💡 later — Shivam: "let's not do that immediately" |
| — | UI polish / central platform | ❌ not ours — Shivam has a separate UI dev; keep ours "bare minimum demoable" |

## 4e. ✅ The workflow registry — views run WORKFLOWS, never module steps

`STEPS` used to expose 3 composites **plus 11 raw module steps** (`verify_noi`, `classify_rows`,
`sections`, …) — **none of which anything ever called**. Loose node handles are the same hazard as
the `run_feedback` flag one level up: they invite a caller to assemble its own pipeline (skip a
node, reorder, re-enter mid-stage). Pruned to **named workflows only**, each a complete transition
`<stage>_<user action>`:

```python
STEPS = {
    "stage1_parse":          stage1,                # upload        → parse up to the anchor lock
    "stage1_check_anchors":  check_anchors,         # gate          → re-verify picks (read-only)
    "stage2_classify":       classify,              # gate confirm  → Stage 2 (AI on NOI fail)
    "stage2_reverify":       reverify,              # Stage-2 edit  → re-verify NOI (no AI)
    "stage3_mapping":        stage3_mapping,        # review submit → rulebook + AI fallback
    "stage3_update_mapping": stage3_update_mapping, # Stage-3 edit  → apply a mapping override
}
```
**A new need = a new workflow, never a new handle.**
Tests don't use the registry — they import modules directly and mock the AI agents.

**Stage 3 is now a real workflow too.** It used to be hand-assembled *in the UI*
(`bridge.run_mapping` did rulebook-load → adapter → `map_results` → `run_ai_mapping` → raw state
write), and the mapping-edit path was worse — `_apply_row_update` lived in a **view** and the
bridge raw-wrote `state["mapping"]`. Moved into the pipeline: `load_latest_rulebook`
(`config/rulebook_utils`), `res_from_state` (`legacy_adapter`), `apply_row_edit` (`map_blocks`).
The bridge is now only *load state → run named workflow → save state*, and every stage is runnable
without Django. **The mapping logic itself was NOT rebuilt** — the rulebook cascade is sound; only
its vocabulary is legacy (`type`/`statement_side` vs our `class`/`section`), which is W5's job.

---

## 4d. ✅ Stage-2 classification editing — DONE (meeting item #6)

Per-row class dropdowns on the review page + a `stage2_reverify` workflow. **No `manual_fix`
caller flag** — that would repeat the `run_feedback` mistake (§4b); the user's edit enters as
*data* (`class_edits={row: CLASS}`) and the page re-enters a named workflow.

**`stage2_reverify` = apply_edits → `verify_noi` → `flag_low_confidence`.** It re-enters the
SAME `noi` node the first pass used (not a copy, not a hand-built dict), so the number on the
page is always the pipeline's number. Deliberately:
- **No re-classify** — recomputing the scores from the signals would overwrite the edit and show
  the user their change vanishing. That is exactly what the old Recompute did (§4b).
- **No AI** — the diagnosis had its turn in `classify`; re-running it per edit would fight the
  user and cost an LLM call per dropdown.
- **No sections re-run** — a section is positional (which side of the locked anchors a row sits
  on), so a class edit cannot move one. *(verified in `sections.assign_sections`)*
- **No lock on manual rows.** The earlier design had `source="manual"` join `feedback.locked`;
  dropped as unnecessary — nothing re-runs after an edit, so there is nothing to lock against,
  and locking would punish a user who clicked a dropdown just to look.
- **Anchors refused.** `locked` = R / E / NOI + expense split rows — the NOI target can't be
  moved. The page also offers no dropdown on them; the workflow doesn't rely on the page for that.

**Provenance lives ON THE ROW**, not in the history: `source ∈ {auto, ai, manual}` +
`source_reason`. The design first said "badge from the tag, reason from `feedback.history`" —
**that could not work**: `save_state` strips `feedback`, and `classify` folds only a 4-field
summary into `classification.diagnosis`, so the AI's per-row reasons never survive to the review
page. `apply_corrections` (shared by the AI loop and the edit path, `source=` picks which) now
stamps both onto the row, where they persist with `classification.classified` for free. Display
only — **no behaviour hangs off the tag.** Grid-wide snapshots were considered and deferred:
right for revert/audit, but the badge+tooltip need is met by the tag at ~3× less state.

**UI:** dropdown on every non-anchor row; `AI` badge (tooltip = the diagnosis's reason) /
`edited` badge; changing a dropdown disables **Save & Continue** until Re-verify runs, so an
unapplied edit can never be what gets mapped.

**Still open — the "AI suggestions" button** (an explicit on-demand `diagnose` re-entry showing
proposals rather than applying them). Not built; `feedback.history` already records every
iteration (row, from→to, reason, fail-cols before→after) and would be its data source — but it
is stripped at save, so this needs the history persisted first.

---

## 5. 💡 Other remaining items

- 🔨 **`tests/` folder (definite, not now)** — no test suite exists; the only checks are
  throwaway scratchpad scripts that will rot. Plan: fixture **test state** (a saved `state.json`
  per format) so individual `run(state)` steps are testable in isolation, plus full-graph runs
  with `run_structure_agent` / `run_diagnosis_agent` mocked. This is what replaces the caller
  flags we deleted.
- 💡 **Export the reviewed/mapped T12** (Excel/CSV out of data_review) — a convenience, not core
  functionality. The old batch had `utils/*_to_excel` exporters (dying with W2). Deferred.
- 🐞 **The flow has no terminal state** — nothing sets `Upload.status = complete`;
  `Upload.STEP_ANALYTICS` is declared but unreachable, so every run stays `draft`. (The run-state's
  own `step` field — "locked"/"classified" — tracks pipeline progress, which is a different thing.)
  Resolve when the ending is decided (analytics page, or just mark complete at data_review).
- **Confidence-threshold tuning** — the low-confidence flag margin (0.15) needs calibration
  against a few genuinely-ambiguous labelled files.
- **Analytics page** — the last unbuilt UI page (charts/metrics over the mapped numbers).
- **Rulebook coverage** — add the new vendors' line-item terms so fewer rows fall to AI mapping
  (a rulebook-building task, not code).
- **Auto sign-normalization** for negative-expense vendors downstream (today it's the manual
  `flip_sign` on data_review).
- **Learning loop** — when a user confirms an anchor with novel wording at the gate, add that
  term back into `anchor_keywords.json` so next time it's automatic. (Less critical if we adopt
  #1, since keywords stop being a gate.)

---

## Suggested order

Done: **#4** (view logging) → **#1** (arithmetic-first anchors) → **#2** (deterministic-first
structure) → **#3 / #3b** (subsection + tolerance fixes). The deterministic core of the
new workflow is now complete: 23/24 raw sellers lock + pass NOI with **no AI**.

Next candidates: **Mirador bug** (§3c — one broken file) · **#5 analytics** (visible deliverable) ·
**W1** config-driven known formats · **W2** delete dead old-batch code · rulebook coverage ·
sign-normalization · learning-loop. (Learning-loop is now low value — #1 made keywords a ranker,
not a gate.)

> Note: #1 makes the **learning loop** in §5 much less critical — keywords no longer gate the
> lock, so a novel anchor term no longer *has* to be added to `anchor_keywords.json` to lock;
> adding it now only bumps that triple's rank (AUTO/DERIVED labeling), not whether it locks.
