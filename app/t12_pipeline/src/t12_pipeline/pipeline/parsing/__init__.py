"""Anchor-first T12 parsing pipeline (ported from the analysis notebook).

Flow: format detect → column resolve (template/AI) → dynamic extract → anchor lock
(R−E=NOI) → classify + fact override → section from anchors → NOI verify → diagnosis.
Each module is a set of pure functions; `run_parse` wires them into stages.
"""
