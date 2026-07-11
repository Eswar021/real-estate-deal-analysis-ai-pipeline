# Row Classification — `code_in_a_desc_in_b` Format

**Files using this format:** Carmel Woods T12 09-25, Pointe Inverness T12 11-25, Willows of Coventry T12 11-25

---

## What the Excel looks like

Every row has an account code in **col A** and a description in **col B**.
The description's leading whitespace in col B is the key structural signal.

```
Col A         Col B
────────────  ──────────────────────────────────
4000-0002     " REVENUE"                ← 1 space + ALL CAPS  →  HEADER
4002-0000     " GROSS POTENTIAL RENT"   ← 1 space + ALL CAPS  →  HEADER
4005-0000     "    Rent"                ← 4 spaces            →  DATA
4006-0000     "    Loss or Gain to Lease"                      →  DATA
4099-9999     "TOTAL GROSS POTENTIAL RENT"  ← 9999 code       →  SUBTOTAL
4400-0000     "INVESTMENT MANAGEMENT REVENUE"  ← no indent    →  DATA
4999-9999     "TOTAL REVENUE"           ← 9999 code           →  SUBTOTAL (EGI flip)
6999-9999     "NET OPERATING INCOME"    ← 9999 code           →  SUBTOTAL (NOI flip)
```

The checks happen **in strict order** — the first matching branch wins and the row is returned immediately. Later branches are never evaluated.

---

## Decision Tree

```mermaid
flowchart TD
    START([Read row:\na = col A stripped\nb = col B stripped\nb_raw = col B with original spaces])

    START --> CHECK_EMPTY{a is empty\nAND b is empty?}
    CHECK_EMPTY -- YES --> EMPTY([EMPTY — skip row])
    CHECK_EMPTY -- NO --> CHECK_CODE

    CHECK_CODE{Does col A match\n^\d4-\d2to4\$\ne.g. 4005-0000?}

    CHECK_CODE -- YES, and col B has text --> CHECK_9999
    CHECK_CODE -- YES, but col B is empty --> EMPTY2([EMPTY — orphan code, skip])
    CHECK_CODE -- NO, A has plain text, B empty --> HEADER_A([HEADER\ndescription = col A\ne.g. 'SECTION NAME'])
    CHECK_CODE -- NO, A is empty, B has text --> EMPTY_A_BRANCH

    CHECK_9999{Does code end\nin 9999?\ne.g. 4999-9999}
    CHECK_9999 -- YES --> SUBTOTAL_9999([SUBTOTAL\ndescription = col B\ne.g. row 48: TOTAL REVENUE\nrow 158: NET OPERATING INCOME])
    CHECK_9999 -- NO --> CHECK_INDENT

    CHECK_INDENT{b_raw starts\nwith 4 spaces?}
    CHECK_INDENT -- YES --> CHECK_4SP_TOTAL{_is_total_text\ncol B?}
    CHECK_4SP_TOTAL -- YES --> SUBTOTAL_4SP([SUBTOTAL\ne.g. '    Total Bad Debt'])
    CHECK_4SP_TOTAL -- NO --> DATA([DATA\ne.g. row 9: 'Rent'\nrow 13: 'Concessions 1x'])

    CHECK_INDENT -- NO --> CHECK_1SP{b_raw starts with\n1 space AND\nb is ALL CAPS?}
    CHECK_1SP -- YES --> CHECK_1SP_TOTAL{_is_total_text\ncol B?}
    CHECK_1SP_TOTAL -- YES --> SUBTOTAL_1SP([SUBTOTAL\ne.g. ' TOTAL ADMINISTRATIVE'])
    CHECK_1SP_TOTAL -- NO --> HEADER_B([HEADER\ne.g. row 6: 'REVENUE'\nrow 8: 'GROSS POTENTIAL RENT'])

    CHECK_1SP -- NO --> CHECK_FALLBACK{_is_total_text\ncol B?}
    CHECK_FALLBACK -- YES --> SUBTOTAL_FB([SUBTOTAL\nkeyword fallback])
    CHECK_FALLBACK -- NO --> DATA2([DATA\ne.g. row 22: 'INVESTMENT\nMANAGEMENT REVENUE'])

    EMPTY_A_BRANCH{_is_total_text\ncol B?\nor has numbers\nin cols C onward?}
    EMPTY_A_BRANCH -- YES --> SUBTOTAL_EA([SUBTOTAL\ncomputed grand total row\ne.g. A=empty, B=NET OPERATING INCOME\nin files without 9999 codes])
    EMPTY_A_BRANCH -- NO --> SUBTOTAL_EA2([SUBTOTAL\nalways treated as subtotal\nif A empty and B has text])
```

---

## Step-by-step with real Carmel Woods rows

The key thing to understand: **each check is an early return**. Once a branch matches, the function exits immediately. The row never reaches later checks.

### Row 21 (empty row)
```
Col A = ""    Col B = ""
→ Step 1: both empty → EMPTY  ✓  (never reaches any other check)
```

### Row 9 — `"4005-0000"` / `"    Rent"` → DATA
```
Step 1: not both empty           → continue
Step 2: "4005-0000" matches ^\d{4}-\d{2,4}$  → has_code = True
        col B = "    Rent" (non-empty)         → enter the has_code+b branch
Step 3: "4005-0000" ends in 9999? No           → continue
Step 4: b_raw = "    Rent" starts with 4 spaces? YES → enter 4-space branch
        _is_total_text("Rent")? No             → DATA, "Rent"  ✓
```

### Row 6 — `"4000-0002"` / `" REVENUE"` → HEADER
```
Step 1: not both empty           → continue
Step 2: "4000-0002" matches      → has_code = True, col B non-empty
Step 3: ends in 9999? No         → continue
Step 4: b_raw = " REVENUE"
        starts with 4 spaces? No → skip
        starts with 1 space AND "REVENUE".upper() == "REVENUE"? YES → enter 1-space+CAPS branch
        _is_total_text("REVENUE")? No → HEADER, "REVENUE"  ✓
```

### Row 11 — `"4099-9999"` / `"TOTAL GROSS POTENTIAL RENT"` → SUBTOTAL
```
Step 1: not both empty           → continue
Step 2: "4099-9999" matches      → has_code = True, col B non-empty
Step 3: ends in 9999? YES        → SUBTOTAL, "TOTAL GROSS POTENTIAL RENT"  ✓
        (function exits here — never checks indentation or keywords)
```

### Row 20 — `"4399-9999"` / `"NET RENT REVENUE"` → SUBTOTAL
```
Step 3: "4399-9999" ends in 9999? YES
        → SUBTOTAL, "NET RENT REVENUE"  ✓
        (Note: no "Total" prefix but the 9999 code catches it anyway — no keywords needed)
```

### Row 22 — `"4400-0000"` / `"INVESTMENT MANAGEMENT REVENUE"` → DATA
```
Step 2: has_code = True, col B non-empty
Step 3: ends in 9999? No
Step 4: b_raw = "INVESTMENT MANAGEMENT REVENUE"
        starts with 4 spaces? No → skip
        starts with 1 space? No  → skip  (no leading space at all)
        _is_total_text("INVESTMENT MANAGEMENT REVENUE")? No → DATA  ✓
```

### Row 48 — `"4999-9999"` / `"TOTAL REVENUE"` → SUBTOTAL  ← **EGI (income phase flip)**
```
Step 3: "4999-9999" ends in 9999? YES
        → SUBTOTAL, "TOTAL REVENUE"  ✓
        (detect_blocks state machine then sees "total revenue" in GRAND_INCOME_TOTAL_MARKERS
         and flips income_phase_complete = True — all rows after this become expense)
```

### Row 158 — `"6999-9999"` / `"NET OPERATING INCOME"` → SUBTOTAL  ← **NOI flip**
```
Step 3: "6999-9999" ends in 9999? YES
        → SUBTOTAL, "NET OPERATING INCOME"  ✓
        (detect_blocks state machine sees "net operating income" in GRAND_NOI_MARKERS
         and flips capex_phase_complete = True — all rows after this become capex)
```

---

## Why the 9999 code is the most reliable signal

In Carmel Woods, every single section total has a `xxxx-9999` code.
This covers: `TOTAL GROSS POTENTIAL RENT`, `NET RENT REVENUE`, `TOTAL REVENUE`, `NET OPERATING INCOME` — none of these need keyword matching to be classified as SUBTOTAL.

The keyword path (`_is_total_text`) only fires for:
- 4-space-indented rows whose description starts with "Total" (e.g. `    Total Bad Debt Recovery`)
- Edge-case fallback rows with no indentation pattern

---

## Where keywords are actually needed

| Scenario | Example | Why keyword needed |
|---|---|---|
| 4-space row with "Total" in description | `    Total Bad Debt Recovery` | Indented + "Total " prefix → `_is_total_text` detects it |
| Empty A + exotic grand total label | A="", B="Collectible Rental Revenue" | No 9999 code, no "Total" prefix → numeric fallback |
| 1-space ALL-CAPS total | ` TOTAL CONTROLLABLE EXPENSES` | Caught by `_is_total_text` after 1-space+CAPS branch |

In practice, the 9999 code handles every **structural section boundary** in this format.
Keywords are a safety net for intermediate subtotals and exotic labels, not the primary signal.
