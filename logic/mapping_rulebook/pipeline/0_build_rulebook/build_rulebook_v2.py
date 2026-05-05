"""
build_rulebook_v2.py — Rulebook V2 Pipeline Step 2

Reads all per-file extracted mapping JSONs (from extract_mappings_v2.py),
resolves conflicts using source-type priority, and outputs a clean rulebook.

Conflict resolution rules (applied per description):
  1. No conflict          — all files agree → accepted as-is
  2. Override beats Auto  — any file with source_type="override" wins over files
                            that only have source_type="auto"
  3. Override vs Override — multiple files have overrides pointing to different
                            categories → most common override wins; flagged in audit
  4. Auto vs Auto         — no override in any file, different auto mappings →
                            majority vote wins; tied descriptions are flagged

Baseline:
  Reads db/mapping_rule_book_v2.json as a starting baseline (if it exists),
  then merges all extracted-file entries on top. New files always take precedence
  over the baseline for the same description.

Output:
  output_docs/mapping_rulebook_v2/mapping_rule_book_v2.json  — drop-in rulebook
  output_docs/mapping_rulebook_v2/rulebook_v2_audit.json     — full resolution log

Run extract_mappings_v2.py first.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    EXTRACTED_MAPPINGS_V2_DIR,
    RULEBOOK_DB_V2_PATH,
    RULEBOOK_V2_OUTPUT_DIR,
)

RULEBOOK_OUT_PATH = RULEBOOK_V2_OUTPUT_DIR / "mapping_rule_book_v2.json"
AUDIT_OUT_PATH    = RULEBOOK_V2_OUTPUT_DIR / "rulebook_v2_audit.json"


# ── 1. Load extracted per-file JSONs ─────────────────────────────────────────

extracted_files = sorted(EXTRACTED_MAPPINGS_V2_DIR.glob("*.json"))

if not extracted_files:
    print(f"No extracted mapping files found in {EXTRACTED_MAPPINGS_V2_DIR}")
    print("Run extract_mappings_v2.py first.")
    sys.exit(0)

print(f"Loading {len(extracted_files)} extracted file(s)...\n")

# desc_lower → list of {file, final_mapping, source_type}
desc_occurrences = defaultdict(list)
# desc_lower → canonical (un-lowercased) description (first seen)
desc_canonical = {}

for jfile in extracted_files:
    with open(jfile) as f:
        data = json.load(f)
    for row in data.get("rows", []):
        desc      = row["row_description"]
        desc_lower = desc.strip().lower()
        if desc_lower not in desc_canonical:
            desc_canonical[desc_lower] = desc
        desc_occurrences[desc_lower].append({
            "file":          data["file"],
            "final_mapping": row["final_mapping"],
            "source_type":   row["source_type"],
            "override":      row.get("override"),
            "auto_mapping":  row.get("auto_mapping"),
        })


# ── 2. Load baseline rulebook (v2) if it exists ───────────────────────────────

baseline_rulebook = {}
if RULEBOOK_DB_V2_PATH.exists():
    with open(RULEBOOK_DB_V2_PATH) as f:
        baseline_rulebook = json.load(f)
    print(f"Loaded baseline: {RULEBOOK_DB_V2_PATH} ({len(baseline_rulebook)} categories)")
else:
    print(f"No baseline found at {RULEBOOK_DB_V2_PATH} — building from scratch")

# Seed desc_occurrences from baseline (lower priority — files override baseline)
for category, descriptions in baseline_rulebook.items():
    for desc in descriptions:
        desc_lower = desc.strip().lower()
        if desc_lower not in desc_canonical:
            desc_canonical[desc_lower] = desc
        # Mark as baseline; only added if no file-level entry exists
        desc_occurrences[desc_lower]  # ensure key exists (don't add if already there)


# ── 3. Resolve conflicts ──────────────────────────────────────────────────────

def resolve(desc_lower, occurrences):
    """
    Given all file-level occurrences of a description, pick one final_mapping
    and return (chosen_category, resolution_type).

    resolution_type values:
      "clean"              — all files agree, no conflict
      "override_resolved"  — override(s) beat auto mappings
      "override_conflict"  — multiple different overrides; most common wins
      "auto_conflict"      — no overrides; majority vote applied
      "auto_tie"           — no overrides; tie broken alphabetically (flagged)
    """
    # Deduplicate: same file + same mapping counts once
    seen = set()
    deduped = []
    for occ in occurrences:
        key = (occ["file"], occ["final_mapping"])
        if key not in seen:
            seen.add(key)
            deduped.append(occ)

    mappings = [o["final_mapping"] for o in deduped]
    unique_mappings = set(mappings)

    if len(unique_mappings) == 1:
        return list(unique_mappings)[0], "clean"

    # Separate override-sourced vs auto-sourced
    overrides = [o for o in deduped if o["source_type"] == "override"]
    autos     = [o for o in deduped if o["source_type"] == "auto"]

    if overrides:
        # Count override votes per category
        override_votes = defaultdict(int)
        for o in overrides:
            override_votes[o["final_mapping"]] += 1
        max_votes = max(override_votes.values())
        top = [cat for cat, v in override_votes.items() if v == max_votes]
        chosen = sorted(top)[0]  # alphabetical tiebreak among overrides
        res_type = "override_conflict" if len(override_votes) > 1 else "override_resolved"
        return chosen, res_type

    # All auto — majority vote
    auto_votes = defaultdict(int)
    for o in autos:
        auto_votes[o["final_mapping"]] += 1
    max_votes = max(auto_votes.values())
    top = [cat for cat, v in auto_votes.items() if v == max_votes]
    if len(top) == 1:
        return top[0], "auto_conflict"
    # True tie — alphabetical fallback, flagged
    return sorted(top)[0], "auto_tie"


# ── 4. Build rulebook and audit log ──────────────────────────────────────────

rulebook   = defaultdict(set)
audit_rows = []
counts     = defaultdict(int)

for desc_lower, occurrences in sorted(desc_occurrences.items()):
    canonical_desc = desc_canonical[desc_lower]
    chosen, res_type = resolve(desc_lower, occurrences)

    rulebook[chosen].add(canonical_desc)
    counts[res_type] += 1

    # Only log conflicts and overrides (clean entries bloat the audit file)
    if res_type != "clean":
        audit_rows.append({
            "description":      canonical_desc,
            "chosen_category":  chosen,
            "resolution_type":  res_type,
            "sources": [
                {
                    "file":          o["file"],
                    "final_mapping": o["final_mapping"],
                    "source_type":   o["source_type"],
                    "override":      o.get("override"),
                }
                for o in occurrences
            ],
        })


# ── 5. Save outputs ───────────────────────────────────────────────────────────

rulebook_out = {cat: sorted(descs) for cat, descs in sorted(rulebook.items())}

with open(RULEBOOK_OUT_PATH, "w") as f:
    json.dump(rulebook_out, f, indent=2)

audit_out = {
    "summary": {
        "total_descriptions":     len(desc_occurrences),
        "clean":                  counts["clean"],
        "override_resolved":      counts["override_resolved"],
        "override_conflict":      counts["override_conflict"],
        "auto_conflict_resolved": counts["auto_conflict"],
        "auto_tie_broken":        counts["auto_tie"],
        "files_used":             len(extracted_files),
        "baseline_used":          RULEBOOK_DB_V2_PATH.exists(),
    },
    "conflicts": audit_rows,
}

with open(AUDIT_OUT_PATH, "w") as f:
    json.dump(audit_out, f, indent=2)


# ── 6. Print summary ──────────────────────────────────────────────────────────

total_descs = sum(len(v) for v in rulebook_out.values())
print(f"Rulebook v2 built:")
print(f"  Categories:            {len(rulebook_out)}")
print(f"  Total descriptions:    {total_descs}")
print(f"  Clean (no conflict):   {counts['clean']}")
print(f"  Override resolved:     {counts['override_resolved']}")
print(f"  Override conflict:     {counts['override_conflict']}")
print(f"  Auto conflict:         {counts['auto_conflict']}")
print(f"  Auto tie (flagged):    {counts['auto_tie']}")

if counts["override_conflict"] or counts["auto_tie"]:
    print(f"\n  ⚠ {counts['override_conflict'] + counts['auto_tie']} entries need manual review "
          f"— see {AUDIT_OUT_PATH.name}")

print(f"\nSaved rulebook  → {RULEBOOK_OUT_PATH}")
print(f"Saved audit log → {AUDIT_OUT_PATH}")
