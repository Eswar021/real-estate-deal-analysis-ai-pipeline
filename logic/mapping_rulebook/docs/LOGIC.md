# T12 Mapping Pipeline — Logic Reference

How each stage of the pipeline works internally. Covers algorithms, decision rules,
and the reasoning behind non-obvious design choices.

---

## Stage 0 — Rulebook Build

### What the rulebook is

The rulebook is a JSON file structured as:
```json
{
  "Gross Potential Rent": ["Gross Possible Rent", "Gross Potential", "GPR", ...],
  "Repairs And Maintenance": ["Maintenance Repairs", "R&M", ...],
  ...
}
```

The key is Oakdale Capital's canonical category name. The value is every vendor
description variant seen across all historical files that maps to that category.
At runtime, the reverse map is built: `description (lowercased) → canonical category`.

---

### V1 vs V2 rulebook

**V1 (`create_mappings.py`)** reads only the `Final_Mapping` column from each `.xlsm`
file. If two files disagree on the same description, the last file processed wins.
There is no record of which mapping came from a human correction vs an algorithm guess.

**V2** solves this by extracting three columns per row:

| Column | Meaning |
|---|---|
| `Auto Mapping` | What the algorithm suggested automatically |
| `OVERRIDE` | What the human analyst typed to correct it (null if accepted) |
| `Final_Mapping` | The mapping actually used = OVERRIDE if set, else Auto Mapping |

From these, `source_type` is derived: `"override"` if OVERRIDE is non-null, else `"auto"`.
Human overrides are treated as authoritative; auto mappings are treated as guesses.

---

### Extracting rows from `.xlsm` files (`extract_mappings_v2.py`)

Each `.xlsm` file has a `Financials` sheet. The extraction anchor is a cell containing
the text `"COMPLETE MAPPING HERE"`. The data table starts on the row immediately after
that anchor.

**Row boundary:** The table ends at the first row where the Index column (column 0) is
empty. Rows beyond that point are other sheet content and must be ignored. This matches
the boundary logic used when the `.xlsm` files were originally created.

**Type guard on values:** Excel formula results can produce booleans (`True`/`False`),
numbers, or error strings (`#N/A`). Category names must be strings. Any non-string
value from a mapping column is treated as `None` and the row is skipped. This prevents
formula results from appearing as category names in the rulebook.

```python
def normalize(val):
    if not isinstance(val, str):
        return None
    s = val.strip()
    return s.title() if s else None
```

---

### Conflict resolution (`build_rulebook_v2.py`)

After extracting all 19 `.xlsm` files, some descriptions appear in multiple files with
different final mappings. The resolution priority is:

```
Override beats Auto
  └─ If any file has source_type="override" → override votes win regardless of auto count

Override vs Override (rare)
  └─ Multiple files disagree with overrides → most common override wins
  └─ If tied → alphabetical tiebreak; flagged in audit log

Auto vs Auto (no override in any file)
  └─ Majority vote
  └─ If tied → alphabetical fallback; flagged in audit log

No conflict
  └─ All files agree → accepted as-is
```

The five resolution types recorded in the audit log:

| Type | Meaning |
|---|---|
| `clean` | All files agree |
| `override_resolved` | Override(s) beat auto mappings |
| `override_conflict` | Multiple overrides disagreed; most common won |
| `auto_conflict` | No overrides; majority vote applied |
| `auto_tie` | No overrides; tie broken alphabetically — needs manual review |

The output rulebook is written to `output_docs/` only, never directly to `db/`.
This keeps Stage 0 build artifacts separate from the read-only reference snapshots.

---

### Category classification (`category_config.py`)

Each of the 36 canonical categories is classified into one of three buckets:

| Bucket | Count | Used in NOI? |
|---|---|---|
| `REVENUE` | 16 | Yes — added |
| `EXPENSE` | 17 | Yes — subtracted |
| `SKIP` | 3 | No — Capex items below the NOI line |

This classification is stored in
`output_docs/<date>/0_build_rulebook/category_config/category_classification.json`
and loaded by `compute_noi.py` at runtime.

---

## Stage 1 — Per-file Mapping

### Step 1: Format detection (`detect_blocks.py`)

Vendor T12 files come in three structural layouts. The format is detected by sampling
the first 60 rows of the active sheet.

**Format A — Code in Col A, Description in Col B**
*Properties: Willows of Coventry, Pointe Inverness, Carmel Woods*

Account codes like `4002-0000` appear in column A; the human-readable description is
in column B. Detected by counting rows matching the pattern `\d{4}-\d{2,4}`.
Threshold: ≥ 5 matching rows in first 60.

**Format B — Embedded Code in Col A**
*Properties: Brownsburg Crossing, Pebble Brook Village*

Column A contains lines like `5120 - Gross Possible Rent` — the account code is
embedded inside the description text. Detected by counting rows matching
`^\s*\d{4}(\s*-\s*\d*\s*-?\s*)`. Threshold: ≥ 3 matching rows.

**Format C — No Codes, Indent-Based**
*Properties: Echo Park at Perry Crossing*

No account codes at all. Data rows are identified by their indentation level (≥ 2
leading spaces). Falls through if neither Format A nor B conditions are met.

---

### Step 2: Data start row detection

Each file has metadata rows above the financial table (property name, date range,
column headers). The data start row is found by scanning the first 30 rows for:
- The first row containing an account code (Formats A/B) — that row or its header above
- A row containing income/revenue keywords followed by rows with data patterns

---

### Step 3: Column header extraction

The monthly column headers (Jan, Feb, ..., Total) are extracted by scanning upward
from the data start row looking for the row with the most unique non-empty values.
A row with ≥ 10 unique values is treated as the definitive header row (months are
all different). Empty slots in the header are filled in from the row above or below
if they contain "Total".

The table is trimmed at the first "Total" column — any columns beyond that are excluded.

---

### Step 4: Row classification

Each row is classified as `data`, `header`, `subtotal`, or `empty`.

**Format A rules:**

| Condition | Classification |
|---|---|
| Col A matches `DDDD-DDDD`, Col B has text | DATA (default) |
| Col A matches `DDDD-9999` (ends in 9999) | SUBTOTAL (Carmel Woods convention) |
| Col B has ≥ 4 leading spaces | DATA |
| Col A has text, Col B empty, no account code | HEADER |
| Col A empty, Col B has text | SUBTOTAL |

**Format B rules:**

| Condition | Classification |
|---|---|
| Col A matches embedded code pattern | DATA (code stripped from description) |
| Text starts with "Total" or matches grand-total keywords | SUBTOTAL |
| Everything else | HEADER |

**Format C rules:**

| Condition | Classification |
|---|---|
| Text starts with "Total" or matches grand-total keywords | SUBTOTAL |
| Indent ≥ 2 spaces | DATA |
| Indent = 0 + has numeric values in data columns | SUBTOTAL |
| Indent = 0 + no numbers + no "Total" | HEADER |

**Grand-total keywords** (rows containing these are always SUBTOTAL regardless of format):
`net operating income`, `effective gross income`, `net rental revenue`,
`net income`, `net cash flow`, `total income`, `total expenses`, `total revenue`, etc.

---

### Step 5: Section context

As rows are processed in order, the most recently seen HEADER row is tracked as
`section_context`. Every DATA row carries this context field. It tells the AI model
which section of the T12 a line item belongs to (e.g. "Rental Revenue", "Operating
Expenses") without needing to parse hierarchy.

---

### Step 6: Auto-mapping (`map_blocks.py`)

The reverse map is built at runtime by iterating every entry in the rulebook:
```python
reverse_map = {}
for category, descriptions in rulebook.items():
    for desc in descriptions:
        reverse_map[desc.strip().lower()] = category
```

For each DATA row, `description.strip().lower()` is looked up in `reverse_map`.
- Match found → `mapping = category`, `not_found = false`
- No match → `mapping = null`, `not_found = true`

Only exact matches are used. No fuzzy matching, no stemming. This keeps false-positive
rate at zero — an incorrect auto-mapping is worse than no mapping, because it silently
propagates into NOI computation.

---

### Step 7: AI mapping (`find_mapping.py`)

Every row with `not_found: true` is passed to the configured LLM provider via LangChain.

**Prompt design:** The system prompt provides the full list of canonical categories and
instructs the model to choose only from that list. Inventing new category names is
explicitly forbidden. This prevents the AI from creating variants that silently miss
the NOI calculation.

**Structured output:** LangChain's `with_structured_output(AISuggestedMapping)` is used
so the response is a typed Pydantic object, not free text. Fields:
- `suggested_category` — one of the canonical categories
- `confidence` — `"high"` / `"medium"` / `"low"`
- `reasoning` — brief explanation

**Context provided per row:**
- The row description
- `section_context` (nearest header above it)
- Full list of allowed categories

The full prompt and response are saved to `ai_mapping_logs/` for every call.

---

## Stage 2 — NOI Verification

### Why verification is needed

After AI mapping, every DATA row has a category assigned. But if a row was mis-mapped
(e.g. a revenue item classified as an expense), the computed NOI will diverge from the
vendor-reported NOI. Verification catches this before the mapped data is used in analysis.

---

### Extracting vendor-reported NOI (inside `compute_noi.py`)

The vendor-reported NOI is a SUBTOTAL row in the ai_mapped file. The script scans all
SUBTOTAL rows for descriptions that match NOI-related keywords:
`net operating income`, `noi`, `net income`, `net cash flow`, etc.

If multiple candidate rows are found, the last one with numeric values wins — T12 files
sometimes have a preliminary subtotal followed by a final adjusted NOI row at the bottom.

The monthly values and the annual total are extracted from the `values` array of that row.

---

### Computing NOI from mapped rows (`compute_noi.py`)

The current Stage 2 implementation keeps both logical substeps inside `compute_noi.py`:
- extract vendor-reported NOI into `actual_noi/`
- compute our NOI into `computed_noi/`

For each DATA row in the ai_mapped file:
1. Look up its category in `category_classification.json`
2. If `REVENUE` → add its monthly values to the running total
3. If `EXPENSE` → subtract its monthly values from the running total
4. If `SKIP` (Capex) → exclude it entirely
5. If category not found in classification → mark as unclassified; exclude from NOI

The final mapping used is: `auto_mapping` if the row was found in the rulebook, else
`ai_suggested_mapping`.

---

### Comparing actual vs computed (`compare_noi.py`)

Month-by-month comparison with tolerance:

```
tolerance = max($1.00, 0.1% × |actual NOI|)
```

A month PASSES if `|actual − computed| ≤ tolerance`. A file PASSES only if every
month AND the annual total pass.

The `$1.00` floor absorbs rounding differences in cells. The `0.1%` factor scales the
tolerance for large properties — a $1M NOI file would have a $1,000 tolerance, which
is appropriate given that vendors round to the dollar.

A FAIL means something was mis-mapped, double-counted, or missed entirely. The
month-level breakdown in the comparison JSON points to which months diverge, helping
narrow down which rows to investigate.

---

## Design Decisions Summary

| Decision | Choice | Reason |
|---|---|---|
| Exact match only (no fuzzy) | Auto-mapping | A wrong match silently corrupts NOI; no match → AI handles it |
| AI must pick from existing categories | Prompt constraint | Prevents drift — new categories would silently miss NOI calculation |
| Human overrides beat auto in conflict | Rulebook v2 priority | Overrides represent analyst corrections; auto is an algorithmic guess |
| Rulebook output to `output_docs/` only | Never auto-write to `db/` | Keeps runtime build artifacts separate from read-only reference snapshots |
| Row boundary at empty Index cell | `extract_mappings_v2.py` | Sheet content beyond the table would produce false category names |
| `isinstance(val, str)` guard on categories | `normalize()` | Excel formula results (booleans, numbers) must not become category keys |
| `section_context` instead of hierarchy | Block detection | Flat context field is sufficient for AI; full tree was fragile across 3 formats |
| SUBTOTAL values captured | `detect_blocks.py` | NOI verification needs the vendor-reported NOI row values |
| NOI tolerance = max($1, 0.1%) | `compare_noi.py` | Absorbs rounding on small files without masking real errors on large ones |
| Capex excluded from NOI (SKIP bucket) | `compute_noi.py` | Capex rows appear below the NOI line in T12 files; including them would understate NOI |
