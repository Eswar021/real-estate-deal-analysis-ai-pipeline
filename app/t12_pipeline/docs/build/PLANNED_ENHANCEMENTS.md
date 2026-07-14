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

## 4. ✅ View-level debug logging — DONE (report.py removed)

Built: `app/ui/t12_mapping/debug_log.py` (per-page `t12.<page>` loggers; INFO one-liner +
DEBUG anchor/NOI/classified tables) wired into all four views; `LOGGING` block in
`config/settings.py` (console + optional file, `T12_LOG_LEVEL` / `T12_LOG_FILE` env). The old
`report.py` CLI dump was deleted (its report-only helper `reconcile_leaf_data` too). Design below.



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

## 5. 💡 Other remaining items

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
