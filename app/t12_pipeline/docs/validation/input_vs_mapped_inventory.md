# Input ↔ Mapped (Model T12) Inventory

_Generated 2026-08-20. Each raw-T12 **input** (`data/input_T12_docs/`) and its reviewed **Model T12** ground-truth file (`data/mapped_T12_docs/`), for the mapping-accuracy check. A `—` means we don't have a mapped file for that property yet._

**Totals:** 33 inputs · **16 with** a mapped file (the validation set) · 17 without · 26 mapped-only properties (no raw input).

| # | Input file | Detected format | Mapped (Model T12) file |
|---|------------|-----------------|--------------------------|
| 1 | 04.2024-03.2025 T-12 Brackett.xlsx | code in A / desc in B | — |
| 2 | Carmel Woods T12 09-25.xlsx | code in A / desc in B | — |
| 3 | Cornelius Jan 2025 T-12_Month_Statement.xlsx | code in A / desc in B | — |
| 4 | Lincoln Townhomes Seller T12.xlsx | code in A / desc in B | Lincoln Townhomes Model T12.xlsx |
| 5 | Pointe Inverness T12 11-25.xlsx | code in A / desc in B | — |
| 6 | Pratt T12 March 2025.xlsx | code in A / desc in B | — |
| 7 | T12 - Sienna Park (02.2025).xlsx | code in A / desc in B | — |
| 8 | Willows of Coventry T12 11-25.xlsx | code in A / desc in B | 02252026_Willows of Coventry_V4 (1).xlsm |
| 9 | Brownsburg Crossing T12 05-25.xlsx | embedded code in A | — |
| 10 | Creekside Seller T12.xlsx | embedded code in A | Creekside Apartment Homes Model T12.xlsx |
| 11 | Lockhart Seller T-12.xlsx | embedded code in A | Lockhart Model T12.xlsx |
| 12 | Mirador Seller T12 .xlsx | embedded code in A | Mirador Model T12.xlsx |
| 13 | Pebble Brook Village T12 03-25.xlsx | embedded code in A | — |
| 14 | Pebble Brook Village T12 09-25.xlsx | embedded code in A | — |
| 15 | River Point Seller T12 Feb.xlsx | embedded code in A | River Point Model T12.xlsx |
| 16 | River Point West Seller T12.xlsx | embedded code in A | River Point West Model T12.xlsx |
| 17 | Wythe Seller T12.xlsx | embedded code in A | Wythe Model T12.xlsx |
| 18 | Echo Park at Perry Crossing T12 12-24.xlsx | no code | — |
| 19 | Ladera Seller T12.xlsx | no code | Ladera Model T12.xlsx |
| 20 | Link Apartments_12 Month Statement_2025-02-28.xlsx | no code | — |
| 21 | Miars Farm 4.26 T12..xlsx | no code | — |
| 22 | Mural Apartments_12 Month Statement_2025-02-28.xlsx | no code | — |
| 23 | RESERVE AT WHITE ROCK Seller T12.xlsx | no code | Reserve_at_White_Rock Model T12.xlsx |
| 24 | Swiss Gables_12_Month_Statement_ri007_Accrual.xlsx | no code | — |
| 25 | TRAILS AT WHITE ROCK Seller T12.xlsx | no code | TRAILS OF WHITE ROCK Model T12.xlsx |
| 26 | 12_Month_Statement_walocvis_Cash (1).xlsx | unknown (deterministic) | — |
| 27 | Arbor Gates at Buckhead Seller T12.xlsx | unknown (deterministic) | Arbor Gates at Buckhead Model T12.xlsx |
| 28 | Cardinal Seller T12.xlsx | unknown (deterministic) | Cardinal Model T12.xlsx |
| 29 | Chateau in the  Woods T12 08-25.xlsx | unknown (deterministic) | — |
| 30 | Crystal Lake_T-12_04.2026.xlsx | unknown (deterministic) | — |
| 31 | Eleven11 Lexington at Flower Mound Seller T12.xlsx | unknown (deterministic) | Eleven11 Lexington at Flower Mound Model T12.xlsx |
| 32 | Holden Seller T12.xlsx | unknown (deterministic) | Holden Model T12.xlsx |
| 33 | Mesquite Seller T-12.xlsx | unknown (deterministic) | Mesquite Model T12.xlsx |

## Mapped-only properties (reviewed Model T12 exists, but no raw input on hand)

_Not usable for input-accuracy checks until we get their raw vendor T12._

- 02242026_Grande Reserve at Geist_V3- VM..xlsx
- 02242026_Grande Reserve at Geist_V3- VM.xlsm
- 03092026_The Flats at Arrowood_V4 (FULL BUDGET).xlsm
- 03092026_The Tatum_V4 (assumption).xlsm
- 030926_Tides At Eastchase_v3.xlsm
- 031026_Mylo Apartment Homes_V2 - VM.xlsm
- 03112026_Forma at the Park_V1.xlsm
- 03112026_The Rivi_V6 - AW Capex Notes .xlsm
- 03122025_District at Hurstborne_V2.xlsm
- 03182026_The Park at LeBlanc_V3- VM.xlsm
- 03192026_The Jasmine Apartments_V1.xlsm
- 03192026_The Jasmine Apartments_V2 - VM.xlsm
- 03192026_The Park at LeBlanc_V4.1 - AW CapEx.xlsm
- 03242026_Prescott Park Apartments_V1.5.xlsm
- 03272026_Devon on Northgate_V1.xlsm
- 04032026_Villa Del Mar_V1.5.xlsm
- 080425_Jamestown at St. Matthews_v4.xlsm
- 080825_Kenton Reserve_v4.xlsm
- 100325_Park at Eagle Creek_v3.xlsx
- 11182025_Exchange 7272_V1.xlsm
- 11182025_The Hangar_V1.xlsm
- 12042025_The Hathaway at Willow Bend_V1.xlsm
- 12182025_HUB of New Albany_V1.xlsm
- 260312_Melville Apartments_V18-HNW BRIDGE.xlsm
- Golfview Manor - 03.31.2025.xlsm
- Grande Reserve at Geist Model T12.xlsx

---

## Mapping Accuracy — Deterministic (rulebook) validation

_Generated 2026-08-20. For the 16 inputs with a Model T12, we ran the pipeline **without AI** and compared each **rulebook** category to the client's `Final_Mapping` (Model T12 col Z), matched by account description (col T). These `.xlsx` Model T12s were NOT part of the rulebook build (which used the `.xlsm` files), so this is a held-out test._

**Rulebook precision: 1668/1747 = 95.5%** — when the rulebook maps a ground-truth account, it matches the client's mapping ~19 in 20 times. A further **129** ground-truth accounts were left for the AI fallback (accuracy of that portion needs a separate AI run).

Columns: **rows** = data line items · **rulebook-mapped** = mapped deterministically (no AI) · **rb ∩ GT** = rulebook-mapped accounts also present in the Model T12 · **correct** = of those, match the client's Final_Mapping · **precision** = correct / (rb ∩ GT) · **→ AI** = ground-truth accounts the rulebook didn't map (go to the AI fallback).

| Input | rows | rulebook-mapped | rb ∩ GT | correct | precision | → AI |
|-------|-----:|----------------:|--------:|--------:|----------:|-----:|
| Lincoln Townhomes Seller | 118 | 95 | 95 | 95 | 100% | 8 |
| Lockhart Seller | 155 | 144 | 144 | 141 | 98% | 11 |
| Mirador Seller | 113 | 90 | 90 | 88 | 98% | 7 |
| Cardinal Seller | 153 | 136 | 136 | 133 | 98% | 6 |
| RESERVE AT WHITE ROCK | 92 | 83 | 83 | 81 | 98% | 9 |
| TRAILS AT WHITE ROCK | 87 | 78 | 78 | 76 | 97% | 9 |
| Eleven11 | 119 | 110 | 110 | 106 | 96% | 6 |
| River Point Seller T12 Feb | 113 | 107 | 107 | 103 | 96% | 5 |
| River Point West | 113 | 107 | 107 | 103 | 96% | 5 |
| Mesquite | 135 | 108 | 107 | 103 | 96% | 5 |
| Arbor Gates | 112 | 98 | 98 | 94 | 96% | 14 |
| Creekside Seller | 186 | 137 | 129 | 123 | 95% | 9 |
| Ladera Seller | 117 | 101 | 99 | 94 | 95% | 14 |
| Wythe Seller | 195 | 138 | 131 | 123 | 94% | 12 |
| Willows of Coventry | 127 | 124 | 124 | 116 | 94% | 1 |
| Holden Seller | 128 | 109 | 109 | 89 | 82% | 8 |
| **TOTAL (16 files)** | **2063** | | **1747** | **1668** | **95.5%** | **129** |

**Notes:**
- **Holden 82%** is the low outlier — worth reviewing which accounts the rulebook mis-maps there.
- Below-NOI / non-operating rows (mortgage interest, casualty, capex) aren't in the Model T12's operating mapping, so they're correctly excluded from the match set, not counted as errors.
- This measures the **rulebook** only. The **AI-fallback accuracy** (the ~129 accounts above, plus non-ground-truth rows) is a separate pass — it runs live Claude calls, so it's pending your go-ahead.
