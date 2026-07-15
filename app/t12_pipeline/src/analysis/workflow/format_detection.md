# Format Detection — How It Works

Documentation for **Module 3** of the prototype workflow (`t12_workflow.ipynb`).
This module decides which known layout a T12 file uses, or flags it `unknown`.
Everything here is explained the way the code actually does it, and it answers
the questions that came up while building it.

---

## Where it sits

```
File → Pre-flight (reject rent rolls / Model T12) → [Format detection] → known / unknown
```

Format detection is **routing only** — it does not classify rows or read values.
It runs on the raw sheet *before* we know the file's structure, so it can only
use **position-agnostic** signals (patterns we can see without knowing where the
data lives).

The three known formats:

| Format | Layout |
|---|---|
| `code_in_a_desc_in_b` | account code in column A, description in column B |
| `embedded_code_in_a` | code + description merged in column A |
| `no_code` | description in column A, no codes, indentation shows hierarchy |

Anything that doesn't clearly match one of these → `unknown` (handed to the AI
structure agent downstream).

---

## What it looks at

- The **first ~60 rows** (`scan_rows = 60`).
- **Columns A–F** (`NCOLS = 6`).
- Only the raw cell contents.

> **Q: "out of 60, the rows that have content?"** — Yes. We look at rows 1–60.
> Blank/spacer rows are ignored; only rows with actual content matter (see the
> denominator below).

---

## Step 1 — Categorize every cell into one "kind"

For each cell we look at, we put it into exactly **one** of six kinds, checked in
priority order (first match wins, so nothing is double-counted):

| Kind | Cell looks like | Example |
|---|---|---|
| `pure_code` | *only* an account code | `4350-0000` |
| `embedded_code` | code **and** description together | `5120 - Gross Rent` |
| `foreign_code` | a code style we don't support | `5120.0000` (dot), `4010:` (colon), `1-5000-0005` (MRI), `41000-000` (5-digit) |
| `indented_text` | indented plain text, no code | `    Gross Potential Rent` |
| `plain_text` | flush-left plain text | `INCOME`, page titles, dates |
| `numeric` | a number | `133,180` |

`numeric` is **informational only** — it shows where the value columns start; it
does not affect the format decision (more below).

> **Q: "are we not getting embedded and other signals?"** — We compute all six
> kinds for every file. The demo prints them all, including the ones that are
> `0` for a given file (e.g. Lincoln has no `embedded_code` or `foreign_code`,
> so those rows are all zeros — the signal exists, the file just has none).

---

## Step 2 — Build the per-(kind × column) signal grid

Instead of "look at the first text cell of each row," we compute a signal for
**every column separately**. For each of the ~60 rows and each column A–F, we
categorize that cell and tally it.

This gives a `kind × column` grid. Example — **Lincoln** (`code_in_a_desc_in_b`),
shown as `count=fraction`:

```
    kind                  A           B           C           D           E           F
    pure_code       50=0.909     0=0.0       0=0.0       0=0.0       0=0.0       0=0.0
    embedded_code    0=0.0       0=0.0       0=0.0       0=0.0       0=0.0       0=0.0
    foreign_code     0=0.0       0=0.0       0=0.0       0=0.0       0=0.0       0=0.0
    indented_text    0=0.0      38=0.691     0=0.0       0=0.0       0=0.0       0=0.0
    plain_text       4=0.073    12=0.218     1=0.018     1=0.018     1=0.018     1=0.018
    numeric          0=0.0       0=0.0      45=0.818    45=0.818    45=0.818    45=0.818
```

You can read the layout straight off the grid: codes in **A**, descriptions in
**B**, values from **C** onward. That is literally "code in A, description in B."

---

## Normalization — the denominator

Every fraction is:

```
fraction = count / rows_with_text
```

where **`rows_with_text`** = how many of the scanned rows (up to 60) had at least
one **text** cell. For Lincoln that's `55` (the other 5 of the first 60 rows were
blank/spacer rows).

> **Q: "is the denominator per-column, or the same for all columns?"** — It is
> **one global number**, the *same* for every column and every kind. `pure_code`
> in column A = `50/55`, and `numeric` in column C = `45/55` — both divide by 55.

**Why global, not per-column.** A global denominator keeps every signal on the
same baseline, so scores are comparable across columns ("what share of the whole
file's content is a code in column A" vs "…in column D"). A per-column
denominator would divide by "rows where that column has content," which can
mislead — a column with only 3 populated rows, all codes, would score `1.0` and
look like the code column when it isn't. Global avoids that.

**Counts vs fractions.** The demo prints both (`count=fraction`) so the math is
visible: `50=0.909` means 50 rows, and 50/55 = 0.909.

**Side effect.** Because the denominator is global, the kinds in a single column
sum to ≤ 1, and the gap tells you how often that column is empty. Lincoln column
A: `0.909 + 0.073 = 0.982` → column A is populated in ~98% of content rows;
column C: `0.818 + 0.018 = 0.836` → column C is empty in ~16% (the header /
subtotal rows that have no value there).

---

## Step 3 — Score each candidate format

> **Q: "for each format are we using some of the signals to add scores?"** — No.
> Each format's score is **one signal, read directly** from the grid. It is a
> 1:1 mapping, not a weighted sum.

| Candidate | Its score = this one signal |
|---|---|
| `code_in_a_desc_in_b` | `pure_code` fraction in **column A** |
| `embedded_code_in_a` | `embedded_code` fraction in **column A** |
| `no_code` | `indented_text` fraction in **column A** |
| `unknown` | the **largest** `foreign_code` fraction in any column |

For Lincoln that copies four numbers out of the grid → `0.909 / 0.0 / 0.0 / 0.0`.

**Why one signal is enough.** Each format has a signal that's essentially unique
to it — only `code_in_a_desc_in_b` has *pure* codes in column A, only
`embedded_code_in_a` has *merged* code+description in A, only `no_code` has
*indented text with no code* in A. The signals don't overlap, so one dominant
number already gives clean separation. `unknown` is the exception that scans
*all* columns, because foreign codes can appear anywhere (column A for Holden,
column D for Cardinal).

*(Optional, not done today: each score could be a combination — e.g.
`code_in_a_desc_in_b` = "pure code in A" AND "description in B" — for extra
robustness in odd edge cases. The single signal is enough for every file we've
seen, so we kept it simple.)*

---

## Step 4 — Decide (no penalties)

Two rules turn the scores into a decision. Neither dampens the known scores —
`unknown` wins on its own evidence.

1. **Structural gate.** Where do codes dominate? Sum the code kinds
   (`pure_code + embedded_code + foreign_code`) per column and find the top
   column. Our three known formats are all anchored in **column A**; if codes
   dominate some *other* column, the file spreads codes across columns
   (hierarchical / TREE layout) → `unknown`.

2. **Threshold / dominance.** Otherwise take the highest-scoring candidate. If
   the best known score is below `DECISION_THRESHOLD` (0.15), or `unknown`
   outscores every known format → `unknown`. Else → that known format.

> **Q: "wasn't the old penalty biased?"** — Yes, and we removed it. The earlier
> version multiplied the known scores by 0.3 whenever it saw foreign codes or a
> wide spread — a hack that assumed "unknown looks like *these specific things*."
> Now `unknown` is scored by **positive evidence** (foreign codes) plus the
> structural gate, symmetrically with the others. A brand-new format we've never
> seen still lands in `unknown` naturally: if it matches no known signature, all
> known scores are ≈ 0 → below threshold → `unknown`, even with no foreign codes
> and a narrow column spread (this is exactly how Chateau is caught).

---

## Worked examples

**Lincoln → `code_in_a_desc_in_b`**
`pure_code` in A = 0.909; codes dominate column A; 0.909 ≥ 0.15 → known.

**Ladera → `no_code`**
`indented_text` in A = 0.843; no codes at all (structural gate skipped);
0.843 ≥ 0.15 → known. (`numeric` starts in column B → no code column, values
right after the description.)

**Cardinal → `unknown`** *(reason: codes dominate column D)*
`foreign_code` spread A=0.117 / C=0.033 / D=0.55 / E=0.15. Codes dominate
**column D**, not A → structural gate → `unknown`.

**Holden → `unknown`** *(reason: foreign codes dominate)*
`foreign_code` in A = 0.717 (colon codes), all known scores 0. Codes dominate
column A (so the structural gate doesn't fire), but `unknown` (0.717) beats every
known format (0.0) → `unknown`.

---

## The `numeric` signal

Included in the grid but **not used in the decision**. It reveals the file's shape:

- Lincoln: numbers start in **column C** → A=code, B=description, values from C.
- Ladera: numbers start in **column B** → A=description, no code column.
- Cardinal: **no** numbers in A–F → values pushed past column F (another TREE tell).

It's there for inspection and to inform later modules, not to route the file.

---

## Robustness to new formats

The design degrades gracefully. A genuinely new layout ends up `unknown` through
one of three independent paths:

1. Weird code style → lands in `foreign_code` → `unknown` score rises.
2. Codes not in column A / spread across columns → structural gate → `unknown`.
3. None of the above (no codes, flush-left, single column) → all known scores
   ≈ 0 → below threshold → `unknown`.

No single "unknown detector" to fool; it's caught by absence of known evidence.

---

## Validation

Tested on 13 labeled files (all three known formats × multiple files + all known
unknown formats): **13/13 correct.**

| Format | Files | Result |
|---|---|---|
| `code_in_a_desc_in_b` | Lincoln, Carmel, Willows | ✓ |
| `embedded_code_in_a` | Creekside, Brownsburg, Pebble Brook | ✓ |
| `no_code` | Ladera, Echo Park | ✓ |
| `unknown` | Cardinal, Holden, Crystal Lake, Eleven11, Chateau | ✓ |

---

## Tunable knobs

| Constant | Meaning | Current |
|---|---|---|
| `scan_rows` | how many rows to sample | 60 |
| `NCOLS` | how many columns to scan (A–F) | 6 |
| `DECISION_THRESHOLD` | minimum known-format score to accept | 0.15 |

---

## What this module deliberately does NOT do

- It does not build the **structure map** (which exact columns are description /
  values). That's a later module. The per-column grid *could* produce it, but we
  keep this module scoped to the format decision only.
- It does not classify rows (data / header / subtotal) or compute NOI.
- For `unknown` files it makes no guess — it hands off to the AI structure agent.
