"""Runtime rulebook learning — fold user-approved mappings into a NEW rulebook snapshot.

Triggered when the user clicks "Add to rulebook" on data_review. Writes a fresh timestamped
snapshot to db/rulebooks/ (never mutates the live file), so `load_latest_rulebook` picks it up
on the next run and every old snapshot stays for rollback. This is the one RUNTIME path allowed
to write to db/rulebooks/ (alongside `build_rulebook.run`).

v1 logic — three cases per approved `description -> category`:
  1. key has no definite mapping today (new, or currently `unresolved`)  -> add to `certain`
  2. key already maps to the SAME category                               -> skip (reinforce)
  3. key maps to a DIFFERENT category (conflict)                         -> move to `unresolved`
`contextual` entries are hand-crafted, so approvals for those keys are left untouched.
"""
import json
import os
from datetime import datetime

from t12_pipeline.config.paths import DB_RULEBOOKS_DIR
from t12_pipeline.config.rulebook_utils import (load_latest_rulebook, normalize_lookup_key,
                                                validate_rulebook)


def _resolve(key, rulebook):
    """(state, current_mapping) for a key. state ∈ {contextual, definite, unresolved, absent}.
    Both 'unresolved' and 'absent' get promoted to `certain` on approval, but are counted
    separately (an unresolved→certain move is the useful validation signal)."""
    if key in rulebook["contextual"]:
        return "contextual", None
    if key in rulebook["certain"]:
        return "definite", rulebook["certain"][key]["mapping"]
    if key in rulebook["no_conflict"]:
        return "definite", rulebook["no_conflict"][key]["mapping"]
    if key in rulebook["unresolved"]:
        return "unresolved", None
    return "absent", None


def apply_approved(approved, rulebook, source=""):
    """Fold `approved` (list of {description, category}) into `rulebook` IN PLACE (v1 rules).
    Returns a summary. De-dups the batch (last category wins for a repeated description)."""
    prov = {"source": "learned", "learned_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    if source:
        prov["learned_from"] = source

    latest = {}
    for a in approved:
        desc, cat = (a.get("description") or "").strip(), (a.get("category") or "").strip()
        note = (a.get("review_note") or "").strip() or None
        key = normalize_lookup_key(desc)
        if key and cat:
            latest[key] = (desc, cat, note)

    summary = {"added": 0, "promoted": 0, "reinforced": 0, "conflicted": 0, "notes_updated": 0,
               "skipped_contextual": 0, "conflicts": [], "added_list": [], "promoted_list": []}
    for key, (desc, cat, note) in latest.items():
        state, current = _resolve(key, rulebook)
        if state == "contextual":
            summary["skipped_contextual"] += 1
        elif state in ("absent", "unresolved"):
            rulebook["unresolved"].pop(key, None)                       # promote if it was unresolved
            rulebook["certain"][key] = {"row_description": desc, "mapping": cat,
                                        "review_note": note, **prov}
            if state == "unresolved":                                   # moved out of review → certain
                summary["promoted"] += 1
                summary["promoted_list"].append([desc, cat])
            else:                                                       # brand-new account
                summary["added"] += 1
                summary["added_list"].append([desc, cat])
        elif current == cat:
            if note is not None:                                       # let a fresh note update the entry
                entry = rulebook["certain"].get(key) or rulebook["no_conflict"].get(key)
                if entry is not None and entry.get("review_note") != note:
                    entry["review_note"] = note
                    summary["notes_updated"] += 1
            summary["reinforced"] += 1
        else:  # conflict — never silently overwrite; flag for review
            rulebook["certain"].pop(key, None)
            rulebook["no_conflict"].pop(key, None)
            rulebook["unresolved"][key] = {
                "row_description": desc, "reason_type": "user_conflict",
                "review_note": f"User approved '{cat}' but the rulebook had '{current}'. Needs review.",
                "historical_candidate_mappings": [current, cat], **prov}
            summary["conflicted"] += 1
            summary["conflicts"].append([desc, current, cat])
    return summary


def write_snapshot(rulebook):
    """Write a NEW timestamped snapshot atomically (temp → rename); return its Path."""
    validate_rulebook(rulebook)
    DB_RULEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = DB_RULEBOOKS_DIR / f"mapping_rulebook_{datetime.now().strftime('%Y_%m_%d_%H%M%S')}.json"
    tmp = dest.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(rulebook, f, indent=2)
    os.replace(tmp, dest)     # atomic — a half-written file can never become the live rulebook
    return dest


def learn_from_approved(approved, source=""):
    """Load the latest rulebook, fold in the approved mappings, write a new snapshot (only if
    anything actually changed). Returns the summary with `snapshot` set to the new path or None."""
    rulebook = load_latest_rulebook()
    summary = apply_approved(approved, rulebook, source=source)
    changed = (summary["added"] or summary["promoted"] or summary["conflicted"]
               or summary["notes_updated"])
    summary["snapshot"] = str(write_snapshot(rulebook)) if changed else None
    return summary
