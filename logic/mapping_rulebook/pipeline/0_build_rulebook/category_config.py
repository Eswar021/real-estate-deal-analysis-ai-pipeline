"""
category_config.py

Reads all canonical categories from the rulebook and classifies each as:
  REVENUE  — income items (positive income or negative adjustments to revenue)
  EXPENSE  — operating expense items (factor into NOI)
  SKIP     — below-NOI-line items (capex, debt service — do NOT factor into NOI)

Outputs db/category_classification.json for use by the NOI verification agents.

Run this whenever new categories are added to the rulebook to keep the
classification file up to date. It will warn about any unclassified categories.

Usage:
    python pipeline/0_build_rulebook/category_config.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    CATEGORY_CLASSIFICATION_PATH)
from config.rulebook_runtime import get_active_rulebook_name, get_active_rulebook_path

ACTIVE_RULEBOOK_PATH = get_active_rulebook_path()
ACTIVE_RULEBOOK_NAME = get_active_rulebook_name()


# ── Manual classification of all 36 canonical categories ─────────────────────
# Update this dict whenever new categories are added to the rulebook.

CLASSIFICATION = {
    # ── REVENUE (top-line income and adjustments) ──
    "Gross Potential Rent":                  "REVENUE",
    "(Loss) Gain To Lease":                  "REVENUE",
    "Vacancy Loss":                          "REVENUE",
    "Non Revenue Units":                     "REVENUE",
    "Rental Concessions":                    "REVENUE",
    "Bad Debt":                              "REVENUE",
    "Other Income Ops":                      "REVENUE",
    "Other Income: Value Add":               "REVENUE",
    "Parking Income":                        "REVENUE",
    "Laundry And Vending":                   "REVENUE",
    "Utility Rebill - Electric":             "REVENUE",
    "Utility Rebill - Gas":                  "REVENUE",
    "Utility Rebill - Water/Sewer":          "REVENUE",
    "Utility Rebill - Cable, Internet, Other": "REVENUE",
    "Utility Rebill - Trash Removal":        "REVENUE",
    "Utility Rebill - Other":                "REVENUE",

    # ── EXPENSE (operating expenses — factor into NOI) ──
    "Administrative":                        "EXPENSE",
    "Contracted Services":                   "EXPENSE",
    "Insurance":                             "EXPENSE",
    "Management Fee":                        "EXPENSE",
    "Marketing And Retention":               "EXPENSE",
    "Payroll Salaries/Wages":                "EXPENSE",
    "Payroll Burden":                        "EXPENSE",
    "Professional Fees":                     "EXPENSE",
    "Real Estate Taxes":                     "EXPENSE",
    "Repairs And Maintenance":               "EXPENSE",
    "Turnover Expenses":                     "EXPENSE",
    "Utilities Electric":                    "EXPENSE",
    "Utilities Gas":                         "EXPENSE",
    "Utilities Water/Sewer":                 "EXPENSE",
    "Utilities Cable, Internet, Other":      "EXPENSE",
    "Utilities Trash Removal":               "EXPENSE",
    "Utilities Other":                       "EXPENSE",

    # ── SKIP (below-NOI-line — do NOT include in NOI calculation) ──
    "Capex Major":                           "SKIP",
    "Capex Ongoing":                         "SKIP",
    "Capex Rehab / Replace":                 "SKIP",
}


if __name__ == "__main__":
    with open(ACTIVE_RULEBOOK_PATH) as f:
        rulebook = json.load(f)

    rulebook_categories = set(rulebook.keys())
    classified_categories = set(CLASSIFICATION.keys())

    # ── Warn about anything in the rulebook but not classified ───────────────
    unclassified = rulebook_categories - classified_categories
    if unclassified:
        print(f"WARNING: {len(unclassified)} rulebook categories not in CLASSIFICATION dict:")
        for c in sorted(unclassified):
            print(f"  - {c}")
        print("  Add them to CLASSIFICATION in category_config.py before running NOI verification.\n")

    # ── Warn about anything classified but no longer in rulebook ─────────────
    stale = classified_categories - rulebook_categories
    if stale:
        print(f"WARNING: {len(stale)} classified categories not found in rulebook (may be stale):")
        for c in sorted(stale):
            print(f"  - {c}")
        print()

    # ── Build output — only include categories actually in the rulebook ───────
    output = {}
    counts = {"REVENUE": 0, "EXPENSE": 0, "SKIP": 0}

    for category in sorted(rulebook_categories):
        bucket = CLASSIFICATION.get(category, "UNCLASSIFIED")
        output[category] = bucket
        counts[bucket] = counts.get(bucket, 0) + 1

    with open(CATEGORY_CLASSIFICATION_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved: {CATEGORY_CLASSIFICATION_PATH}")
    print(f"  Source rulebook: {ACTIVE_RULEBOOK_NAME} -> {ACTIVE_RULEBOOK_PATH}")
    print(f"  REVENUE:      {counts.get('REVENUE', 0)}")
    print(f"  EXPENSE:      {counts.get('EXPENSE', 0)}")
    print(f"  SKIP:         {counts.get('SKIP', 0)}")
    print(f"  UNCLASSIFIED: {counts.get('UNCLASSIFIED', 0)}")
    if counts.get("UNCLASSIFIED", 0) > 0:
        print("  Run NOI verification only after all categories are classified.")
