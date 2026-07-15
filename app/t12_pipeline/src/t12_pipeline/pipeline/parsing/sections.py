"""Module 11 — Section assignment from the locked anchors.

A row's section is simply which region it falls between the Stage-1 locked anchors:
revenue up to the revenue anchor, expense up to the NOI anchor, capex below it
(a boundary row keeps the state before its flip). No keyword state machine.

Ported verbatim from notebook Module 11 (`assign_sections`).
"""


def assign_sections(classified, final_map):
    """Two-flag positional tag: revenue -> expense (after the revenue anchor) ->
    capex (after NOI). Boundary rows keep the state BEFORE their flip."""
    mh, rev_end, noi_row = (final_map["month_header_row"],
                            final_map["revenue_end_row"], final_map["noi_row"])
    state = "revenue"
    for r in classified:
        row = r["row"]
        if mh is not None and row <= mh:
            r["section"] = "metadata"; continue
        r["section"] = state
        if row == rev_end:
            state = "expense"
        elif row == noi_row:
            state = "capex"
    return classified


def run(state):
    """Step: sections — reads classified, structure_map; assigns each row's section."""
    return {**state, "classified": assign_sections(state["classified"], state["structure_map"])}
