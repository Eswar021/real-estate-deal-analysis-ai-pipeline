# How the T12 Parser Works

Client-facing walkthrough of how we read a T12 Excel file, classify every row,
and decide whether the file's NOI is correct. Plain language, no code.

---

## The 4 row types

Every row in the file ends up as one of these:

| Type | What it is | Example |
|---|---|---|
| **Header** | A section title with no values | "INCOME", "OPERATING EXPENSES" |
| **Data** | A line item with monthly values | "5120 Gross Rent" → 148,349 / 149,119 / … |
| **Subtotal** | A "Total ..." row with values | "Total Income", "Net Operating Income" |
| **Empty** | Blank row | (skipped) |

---

## Step 1 — Recognize the file's layout

T12 files come in different shapes depending on what software the vendor uses.
We currently support three:

| Layout | What it looks like | Example file |
|---|---|---|
| **code_in_a_desc_in_b** | Code in column A, description in column B | Carmel Woods |
| **embedded_code_in_a** | Code + description merged in column A | Pebble Brook, Brownsburg |
| **no_code** | Descriptions only, no codes, indent shows hierarchy | Echo Park |

**How we decide:** sample the first 60 rows of column A and count three signals:

- Strict codes like `4099-9999` → vote for `code_in_a_desc_in_b`
- Embedded codes like `5120 - Gross Rent` → vote for `embedded_code_in_a`
- Indented text without codes → vote for `no_code`

The winner wins. **If no signal is strong enough, the file is rejected** with a
clear "we don't recognize this layout" message — we never silently default
to a layout that won't work.

---

## Step 2 — Classify every row

We walk row-by-row top to bottom and ask the following questions **in this order**.
The first matching rule wins, the row is classified, and we move to the next row.

### Universal rules (apply to all 3 layouts)

These three checks come first because they're the most reliable signals:

1. **Does the description say "Total ..." or match a grand-total keyword?**
   (Keywords: Net Operating Income, Effective Gross Income, Total Revenue,
   Total Expenses, Total Operating Revenues, etc.)
   → **SUBTOTAL**

2. **Does the row have a code and a description, but ZERO values in any
   monthly column?**
   → **HEADER** (it's a section divider, not a real line item)
   *Example: Carmel rows 50/51/52 → "5000-0000 EXPENSES" with blank cells.*

3. **Is the description ALL CAPS without a "Total" prefix?**
   → **HEADER** (it's a section title)
   *Example: "EXPENSES", "CONTROLLABLE EXPENSES", "ADMINISTRATIVE".*

### Layout-specific rules (run after the universal ones)

These only differ in **where** to look — not in **what** counts as data.

#### code_in_a_desc_in_b

| Signal | Classification |
|---|---|
| Code ends in `-9999` | SUBTOTAL |
| Description in col B has 4-space indent + has values | DATA |
| Anything else (with code + description) | DATA |

#### embedded_code_in_a

| Signal | Classification |
|---|---|
| Description has an embedded code + has values | DATA |
| Description has 5+ space indent + has values | DATA |
| Description has any text | HEADER |

#### no_code

| Signal | Classification |
|---|---|
| Description is indented 2+ spaces + has values | DATA |
| Description is flush-left + has numeric values | SUBTOTAL |
| Description is flush-left + no numbers | HEADER |

---

## Step 3 — Tag every row as revenue / expense / capex

Now that every row has a type (header / data / subtotal), we need to know
**which financial section it belongs to**. Every data row gets a
`statement_side` tag of `revenue`, `expense`, or `capex`. This is how we
later know which rows to sum into revenue vs expense.

### The state machine

We walk top to bottom and keep two boolean flags:

```
income_phase_complete = False        ← starts False
capex_phase_complete  = False        ← starts False
```

For each row, the section is decided by reading the two flags:

| `income_phase` | `capex_phase` | Row's section |
|:---:|:---:|---|
| False | False | **revenue** |
| True | False | **expense** |
| True | True | **capex** |

### When do the flags flip?

We watch for two trigger subtotals:

| Trigger | Keywords we match | What it does |
|---|---|---|
| **Income total** | Total Income, Total Revenue, Effective Gross Income, Total Operating Revenues | Flips `income_phase` to True |
| **NOI** | Net Operating Income | Flips `capex_phase` to True |

### The pre-flip subtlety (important)

When we hit the "Total Income" subtotal, what's its own section — revenue or expense?
**Revenue.** That subtotal IS the last row of the revenue block — the flag flips
AFTER we tag it, not before. Same idea for NOI: it's the last expense-side
subtotal, then the flag flips for the rows below it.

A concrete walk-through:

```
Row description        Section    Flags after this row
─────────────────────  ─────────  ──────────────────────────
Gross Rent             revenue    income=F  capex=F
Other Income           revenue    income=F  capex=F
Total Income           revenue    income=T  capex=F   ← flag flips HERE
─────────────────────  ─────────  ──────────────────────────
Repairs                expense    income=T  capex=F
Admin                  expense    income=T  capex=F
Total Expenses         expense    income=T  capex=F
NOI                    expense    income=T  capex=T   ← flag flips HERE
─────────────────────  ─────────  ──────────────────────────
Capex item             capex      income=T  capex=T
```

---

## Step 4 — Flag the three key subtotal rows

Beyond the section tag, three specific subtotal rows get **named flags**
that the NOI verification step uses directly:

| Flag | Meaning |
|---|---|
| `is_total_revenue` | The vendor's stated final revenue total |
| `is_total_expense` | The vendor's stated final expense total |
| `is_noi` | The vendor's stated NOI row |

### How we find them (first pass: keyword match)

For every subtotal row, we check its description against three keyword groups:

| Flag | Keywords searched |
|---|---|
| `is_total_revenue` | Total Income, Total Revenue, Effective Gross Income, Total Operating Revenues |
| `is_total_expense` | Total Expenses, Total Operating Expenses, Total Controllable Expenses, Total Operating Costs |
| `is_noi` | Net Operating Income |

If a subtotal's description contains a matching keyword, that flag gets set to True
on the row.

### Why we need a dedup step (the bug Fix A solved)

A T12 often has the **same keyword appearing on MULTIPLE rows**:

```
Row 12   Net Operating Income (Loss)     ← summary row at the top — no values
...
Row 185  Net Operating Income (Loss)     ← the REAL NOI subtotal — actual numbers
```

If we left both flagged, downstream code couldn't agree on which row to treat
as "the" NOI. The UI might show one, the NOI math might use the other —
producing inconsistent PASS/FAIL results.

### Dedup rule for `is_noi` and `is_total_revenue`

> **When multiple subtotal rows are flagged with the same flag, keep only
> the bottom-most one that has actual numeric values. Unflag the rest.**

For the example above:
- Row 12 has no values → loses its flag
- Row 185 has the actual monthly numbers → keeps its flag

This rule fixed both the Pebble Brook 03-25 PASS-then-FAIL bug and Creekside
Seller's missing Total Expense (it was a downstream side-effect).

### Dedup rule for `is_total_expense` (slightly different)

Some files have multiple "Total Expenses"-style subtotals (e.g. one for
Controllable + one for Non-Controllable + one for the grand total). The rule:

> **Among multiple `is_total_expense` flags, keep only the LAST one that
> appears BEFORE the NOI row.**
>
> If no keyword match at all, fall back to "the last expense-side subtotal
> right above NOI".

This way we always pick the grand-total expense, not an intermediate subsection total.

---

## Step 5 — Verify the NOI

Two numbers are compared:

- **Actual NOI** = the value on the row we flagged as `is_noi` (vendor's stated NOI)
- **Computed NOI** = (sum of all data rows tagged revenue) − (sum of all data rows tagged expense)

If they match (or differ by less than the configured tolerance) → **PASS**.
If they differ → **FAIL** with a warning, and the user can pick different
rows from the dropdowns and click Recompute.

---

## Universal vs layout-specific — what we share

| Check | Universal? |
|---|---|
| "Total ..." / grand-total keyword detection | ✅ Yes — same keyword list across all 3 layouts |
| "No values → header" structural rule | ✅ Yes — applied in all 3 layouts |
| ALL CAPS → header | ✅ Yes (with small differences in how indent factors in) |
| Section state machine (revenue → expense → capex) | ✅ Yes — one shared implementation |
| Key-subtotal flagging (is_noi, is_total_revenue, is_total_expense) | ✅ Yes — one shared implementation |
| **Where the code lives** (col A, embedded, none) | ❌ Layout-specific |
| **Where the description lives** (col A or col B) | ❌ Layout-specific |
| **What "indented" means** (2 vs 4 spaces, in which column) | ❌ Layout-specific |

The universal questions cover **WHAT** the row is (header / data / subtotal).
The layout-specific questions cover **WHERE** to look on the spreadsheet.

---

## Where each step lives in the code

For developers — quick map of which file owns which step:

| Step | What it does | File |
|---|---|---|
| 1 | Recognize the file's layout (or reject) | `pipeline/detection/detect_blocks.py` → `detect_format()` |
| 2 | Classify each row (header / data / subtotal) | `pipeline/detection/formats/<layout>.py` → `classify_row()` |
| 3 | Tag every row's section (revenue / expense / capex) | `pipeline/detection/detect_blocks.py` → state machine inside `classify_file()` |
| 4 | Flag the three key subtotal rows + dedup | `pipeline/detection/annotate_totals.py` → `annotate_file()` |
| 5 | Compute and compare NOI | `pipeline/detection/compute_noi.py` + `compare_noi.py` |

---

## What happens when we can't recognize the layout

We refuse to guess. The file is rejected at upload with:

> "This T12 file uses a layout we don't recognize yet. Our parser supports
> three formats: account codes in column A, embedded codes in column A,
> or indented descriptions in column A. This file appears to use a
> different layout. Please share it with your contact so support can be added."

This is on purpose — silently defaulting to one of the supported layouts
on an incompatible file produces an all-zero result that falsely passes
NOI verification, which is worse than a clear rejection.
