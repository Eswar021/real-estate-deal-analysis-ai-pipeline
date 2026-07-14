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

## 2. 🔨 Deterministic-first structure finder (AI as fallback)

**Today:** known formats use a deterministic template map (`build_known_map`); *unknown*
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

---

## 3. 💡 Subsection derivation — nesting / odd order (no AI)

Subsections are derived arithmetically (`arithmetic_sum_of_above`): a row is a subtotal if its
value = the sum of the consecutive data rows above it. Three cases:

- **Grand totals (R/E/NOI):** handled by the anchor lock, not here. ✅
- **Leaf subtotals:** the arithmetic scan catches them. ✅
- **Nested (subtotal of subtotals):** iterate — once leaf subtotals are found, treat them as
  members and re-scan for the next level up.
- **Odd-ordered (subtotal not right after its members):** finding *which arbitrary set* of rows
  sums to a value is a subset-sum search (expensive + ambiguous) — don't brute-force it; let the
  **classifier's other signals** (bold, "Total" keyword) catch those rare rows.

**Rationale:** subsections are **not load-bearing** — they only feed the "mark subtotal"
override, not the anchors or the NOI check. So we nail the clean + nested cases with math and
let the rare odd ones fall to the classifier score. **No AI needed.**

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

**#4 (quick win) ✅** → **#1 (robustness) ✅** → next: **#5 analytics (visible deliverable)**,
with #2 / #3 / rulebook / sign / learning-loop as follow-ups. Validate the AI path once (needs
`CLAUDE_API_KEY` + a raw unknown-format T12) before #2.

> Note: #1 makes the **learning loop** in §5 much less critical — keywords no longer gate the
> lock, so a novel anchor term no longer *has* to be added to `anchor_keywords.json` to lock;
> adding it now only bumps that triple's rank (AUTO/DERIVED labeling), not whether it locks.
