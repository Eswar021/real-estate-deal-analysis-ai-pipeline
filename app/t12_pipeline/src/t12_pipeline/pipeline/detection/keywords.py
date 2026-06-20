"""
keywords.py — shared keyword constants for Stage 1 detection.

Single source of truth for the keyword groups that drive:
  - The detect_blocks.py state machine (revenue → expense → capex flips)
  - The annotate_totals.py flag assignment (is_total_revenue, is_total_expense,
    is_noi) and dedup logic

The same income/NOI markers used to be defined separately in both files
and could drift out of sync. Defining them once here makes adding a new
vendor keyword a single-file change.

Lowercase, no leading/trailing whitespace — every consumer lowercases the
description before matching, so these are matched as case-insensitive
substrings.
"""

GRAND_INCOME_TOTAL_MARKERS = frozenset({
    "total income",             # Brownsburg, Pebble Brook 03-25
    "total revenue",            # Carmel Woods
    "effective gross income",   # Pebble Brook 09-25, Pointe Inverness, Willows
    "total operating revenues", # Echo Park
})

GRAND_NOI_MARKERS = frozenset({
    "net operating income",  # covers "(Loss)", "Total Net Operating Income", etc.
})

GRAND_EXPENSE_MARKERS = frozenset({
    "total expenses",
    "total operating expenses",
    "total controllable expenses",
    "total expense",
    "total operating costs",
})
