# New T12 Parsing Pipeline — How It Works

How each stage of the new, unknown-format-capable parsing pipeline works (prototyped in `src/analysis/workflow/t12_workflow.ipynb`). Reads top to bottom; each stage feeds the next.

## 1. Pipeline at a glance

1. **Pre-flight** — is this even a T12 to parse?
2. **Raw extraction** — read the Excel once into `cell_grid`.
3. **Format detection** — known layout, or unknown?
4. **Known branch** — per-format feature extraction.
5. **Unknown branch** — deterministic candidate → AI structure map → reconcile → dynamic feature extraction.
6. **Classification** — label every row (7 classes).
7. **Section assignment** — tag each row revenue / expense / capex.
8. **NOI verification** — do the numbers reconcile?

Both branches emit the **same feature vector**, so everything after step 5 is shared.

## 2. Pre-flight

Rejects files that are not T12 inputs, by filename / sheet name:
- **Rent roll** — name or a sheet matches `RR` / `Rent Roll`.
- **Model T12** — name ends in `Model T12.xlsx` (a target template, not an input).

Anything else proceeds.

## 3. Raw extraction — `cell_grid`

Read the workbook **once, losslessly** into `cell_grid`, the single source of truth. Nothing downstream reopens Excel. Per cell we keep: `value`, `formula`, `data_type`, `number_format`, font (`bold`/`italic`/`underline`/`size`/`color`), alignment (`align_h`/`indent`), `fill_color`, `border_top`/`border_bottom`, `comment`, `hyperlink`. Plus sheet-level: `merged_ranges` (critical for hierarchical layouts), `hidden_rows`/`hidden_cols`.

## 4. Format detection

Reads `cell_grid`. Over the first ~60 rows and columns A–F, each cell is bucketed into exactly one **kind**: `pure_code`, `embedded_code`, `foreign_code`, `indented_text`, `plain_text`, `numeric`. This gives a (kind × column) grid of fractions. Known formats are anchored in **column A**, so each format's score is read straight off its column-A signal.

**The known formats:**

| Format | Layout | Example |
|---|---|---|
| `code_in_a_desc_in_b` | account code in col A, description in col B | `4350-0000` \| `Gross Rent` |
| `embedded_code_in_a` | code + description together in col A | `5120 - Gross Rent` |
| `no_code` | description in col A, no codes, indentation = hierarchy | `    Gross Potential Rent` |
| `unknown` | none of the above | foreign codes (`5120.0000`, `4010:`, `1-5000-0005`, `41000-000`) or hierarchical / merged layouts |

**Decision:** the highest column-A known score wins if it clears the threshold (0.15). Two rules force `unknown`: (a) **structural gate** — codes dominate a column other than A (a hierarchical / TREE layout), or (b) all known scores below threshold. Output: `format`, `confidence` (the winning score), `reason`.

## 5. Known branch — per-format feature extraction

One small extractor per known format (`code_in_a_desc_in_b`, `embedded_code_in_a`, `no_code`). Each reads `cell_grid` and turns every row into the shared **feature vector** (section 7). They differ only in where the code / description / values sit for that format.

## 6. Unknown branch

For formats we don't recognise, we build the structure in three steps, then extract.

### 6a. Deterministic candidate (`derive_layout`)

Compute a first-pass layout from `cell_grid` by counting / regex, no AI:
`value_columns` (columns with numbers in many rows), `month_header_row`, `data_start_row`, `description_columns` (text columns left of the values), and the code style (embedded prefix vs a dedicated code column). Rock-solid for the counting fields; a best guess for the interpretive ones.

### 6b. AI structure agent — what it produces

Model **gpt-4.1**. **Input:** the full raw grid **plus** the deterministic candidate as a starting point. **Job:** verify and correct the candidate against the grid (a capable model reads unusual layouts our regex misses), and return one JSON **structure map**:

- **Layout** — `description_columns`, `code_column`, `code_embedded_in_description`, `code_pattern`, `value_columns`, `month_header_row`, `data_start_row`.
- **Sections** — `revenue_end_row`, `expense_end_row`, `noi_row`.
- **Subsection hierarchy** — for every sub-group at every nesting level: `name`, `header_row`, `subtotal_row`. Explicitly includes bold **"repeated-name" subtotals** that carry no "Total" word (e.g. a bold `Payroll` row that totals the payroll lines).

### 6c. Reconcile + arithmetic validation

Merge the candidate (6a) and the AI map (6b) into one **final structure map**, taking each field from its stronger source and flagging disagreements:
- **Counting** fields (`value_columns`, `month_header_row`, `data_start_row`) → deterministic (unambiguous).
- **Interpretive** fields (`description_columns`, code handling) → AI.
- **Arithmetic-validate every subsection**: `subtotal == Σ (its non-subtotal leaf rows)`. Summing only leaves makes this correct for nested roll-ups too. Only validated subsections become anchors downstream.
- **NOI gate**: `revenue − expense ≈ NOI`. FAIL → route to review (auto-diagnosis is a pending stage).

### 6d. Dynamic feature extraction

Drive the extractor off the final structure map → the same feature vector as the known branch, plus the monthly `values` and the validated subsection anchors. For hierarchical layouts, depth is read from **which description column** a row starts in (`column_depth`); for flat layouts, from leading whitespace (`whitespace_depth`).

## 7. The feature vector (signals per row)

Every extractor — known or unknown — emits this same per-row vector:

| Signal | What it is |
|---|---|
| `has_values` / `value_count` | whether the row has monthly numbers, and how many |
| `values` | the raw monthly numbers (12 months + total) |
| `is_bold` | is the description cell bold (a strong subtotal signal) |
| `total_keyword` | description contains "Total …" or a grand-total keyword |
| `has_formula` | any value cell holds an Excel formula |
| `whitespace_depth` | leading spaces before the description (flat-layout hierarchy) |
| `column_depth` | which description column the row starts in (TREE-layout hierarchy) |
| `all_caps` | description is entirely uppercase |
| `position_in_file` | how far down the sheet (0.0 top → 1.0 bottom) |
| `arithmetic_sum_of_above` | the row's value equals the sum of the data rows directly above it |
| `is_subsection_subtotal` / `is_subsection_header` | this row is a validated subsection anchor (unknown branch) |

## 8. Classification (7 classes, score-based)

Every row is scored against **all seven** classes; the highest wins. A class score is a **sum of weighted signals** — positive = evidence for, negative = against. No thresholds, no decision tree — just "which class has the most evidence." All seven scores are printed, plus a per-row breakdown, so every decision is auditable.

**The classes:**

| Class | Core signature |
|---|---|
| `METADATA` | no values, in the title band above the month header |
| `SECTION_HEADER` | no values, shallow, bold/caps (e.g. `INCOME`) |
| `SUBSECTION_HEADER` | no values, deeper, bold (e.g. `Rental Income`) |
| `DATA` | has values, plain (not bold, not "Total", not a metric) |
| `SUBSECTION_SUBTOTAL` | has values; bold and/or "Total …" and/or arithmetic fires; validated subsection anchor |
| `SECTION_SUBTOTAL` | grand total (often ALL-CAPS) at a section-boundary row |
| `COMPUTED_METRIC` | a cross-section metric (NOI / net cash flow) or the NOI row |

**How signals become scores — two tiers.** (1) **AI subsection anchors** from the validated hierarchy — strong and present only on the unknown branch. (2) **Heuristics** as the fallback: `is_bold ⇒ subtotal` (leaf data is plain), the "Total" keyword, `arithmetic_sum_of_above`, `all_caps`, depth, the `month_header_row` band, and the section-boundary rows.

**Worked example** — `Apartment Rent (GPR)` (a plain data line):
- `DATA` = has_values +2, not_bold +2, no_total_word +1, not_metric +1, not_section_boundary +1 = **7.0**
- `SUBSECTION_SUBTOTAL` = has_values +2 = **2.0**  → DATA wins.

Contrast `Total Concessions`: bold +2, arithmetic +1.5, "Total" +1.5, subsection anchor +4, has_values +2 = **11.0** → SUBSECTION_SUBTOTAL.

**Self-check (leaf-DATA reconciliation).** Sum only the `DATA`-class rows in each section — they must equal that section's grand total. A misclassified subtotal double-counts; a misclassified data row under-counts. Passing to the cent on both a nested and a flat file is the proof the classes are right.

## 9. Section assignment

**Two independent branches** determine the section boundaries and cross-verify:
- **Branch A — deterministic keyword match** (mirrors src `annotate_totals`): bottom-most value row whose description matches a grand-total marker (`total income`, `total expense`, `net operating income`). Pure regex — no AI.
- **Branch B — the AI's boundaries** (already returned in 6b; reused, no new call).

Agree → **HIGH** confidence. Disagree → **REVIEW** (the NOI arithmetic decides which is right). This is a triangulation of three independent signals: keyword ⟂ AI ⟂ arithmetic. A **state machine** then tags every row `revenue → expense → capex` (flip to expense after the revenue total, to capex after NOI; a boundary row keeps the state before its flip).

## 10. NOI verification

Two independent measurements, compared **per month AND on the total** (so errors that cancel across months are still caught):
- **Bottom-up** (our row method) — sum the `DATA` rows by assigned section; NOI = revenue − expense; capex excluded.
- **Top-down** (vendor-reported) — read the grand-total rows directly.

`PASS` requires the bottom-up NOI to match the vendor NOI on every column. Mirrors the src `compute_noi` + `compare_noi`.

## 11. Status

**Built and verified** (penny-exact on a nested-hierarchy file and a flat file): pre-flight → raw extraction → format detection → known/unknown branches → classification → section assignment → NOI verification.

**Pending:** per-row confidence + human-review routing (uses the classifier score margins), AI failure diagnosis (the NOI-FAIL branch), and validating the shared classifier on a known-format file.
