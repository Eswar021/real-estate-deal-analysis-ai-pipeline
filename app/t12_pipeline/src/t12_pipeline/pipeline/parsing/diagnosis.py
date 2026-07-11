"""Module 13 — AI Failure Diagnosis (fires only when NOI verification FAILS).

Hands the whole picture to a capable model and asks one thing: is the vendor's data
internally inconsistent (DATA_PROBLEM — unfixable), or did WE mislabel a row
(CLASSIFICATION_PROBLEM — fixable)? Because the anchors are locked, it can only
reclassify rows, never move the NOI target. Ported verbatim from notebook Module 13 —
model via agent_llm_config (DIAGNOSIS_AGENT → Claude Opus).
"""
from typing import Literal

from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from openpyxl.utils import get_column_letter

from t12_pipeline.llm.llm_client import make_llm
from t12_pipeline.config.agent_llm_config import DIAGNOSIS_AGENT

_ROW_CLASS = Literal["METADATA", "SECTION_HEADER", "SUBSECTION_HEADER", "DATA",
                     "SUBSECTION_SUBTOTAL", "SECTION_SUBTOTAL", "COMPUTED_METRIC"]


class ProblemRow(BaseModel):
    row: int | None = Field(default=None, description="the sheet row number that is mislabeled")
    current_class: str | None = Field(default=None, description="the class our pipeline assigned")
    corrected_class: _ROW_CLASS | None = Field(default=None, description="the class it SHOULD be — EXACTLY one of the seven class names, nothing else appended")
    reason: str | None = Field(default=None, description="why, citing the row label and the arithmetic")


class DiagnosisResult(BaseModel):
    # every field defaulted / optional so a partial or null LLM response still parses
    verdict: Literal["DATA_PROBLEM", "CLASSIFICATION_PROBLEM", "UNCERTAIN"] = Field(default="UNCERTAIN", description="the root cause")
    problem_rows: list[ProblemRow] | None = Field(default=None, description="the mislabeled rows (for CLASSIFICATION_PROBLEM); empty otherwise")
    data_inconsistency: str | None = Field(default=None, description="which vendor total is internally inconsistent and by how much (for DATA_PROBLEM); else null")
    user_message: str = Field(default="", description="one or two plain-English sentences for the end user")
    reasoning: str = Field(default="", description="brief explanation of how the verdict was reached")


def render_structure_summary(final_map):
    vc = final_map["value_columns"]
    code = (f"embedded ({final_map['code_pattern']})" if final_map["code_embedded_in_description"]
            else (f"column {final_map['code_column']}" if final_map["code_column"] else "none"))
    return (f"value_columns: {vc[0]}..{vc[-1]}   description_columns: {','.join(final_map['description_columns'])}   codes: {code}\n"
            f"month_header_row: {final_map['month_header_row']}   data_start_row: {final_map['data_start_row']}\n"
            f"revenue_end_row: {final_map['revenue_end_row']}   expense_end_row: {final_map['expense_end_row']}   noi_row: {final_map['noi_row']}\n"
            f"subsection_subtotal_rows (validated): {final_map.get('validated_subsection_subtotal_rows', [])}")


def render_discrepancy(noi_res):
    lines = [f"overall_pass = {noi_res['overall_pass']}",
             "Columns where NOI does NOT reconcile (vendor top-down vs our bottom-up):"]
    for m in noi_res["months"]:
        a, c, ok = m["noi"]
        if ok is False:
            ra, rc, _ = m["rev"]; ea, ec, _ = m["exp"]
            d = None if (a is None or c is None) else round(c - a, 2)
            lines.append(f"  col {m['col']}: NOI vendor={a} ours={c} (delta {d})   "
                         f"revenue vendor={ra} ours={rc}   expense vendor={ea} ours={ec}")
    return "\n".join(lines)


def render_grid_with_labels(grid, classified, final_map):
    """Full raw grid, each content row annotated with OUR class/section."""
    lab = {r["row"]: r for r in classified}
    L = [f"Sheet '{grid['sheet']}': rows 1-{grid['max_row']}, cols A-{get_column_letter(grid['max_col'])}.",
         "Each row: row | COL=value ...  =>  OUR: class/section   (text keeps leading spaces; * = bold)", ""]
    for grow in grid["rows"]:
        parts = []
        for c, cell in sorted(grow["cells"].items()):
            v = cell["value"]
            if v is None:
                continue
            star = "*" if cell["bold"] else ""
            v = round(v, 2) if isinstance(v, (int, float)) else repr(v)
            parts.append(f"{cell['letter']}{star}={v}")
        if not parts:
            continue
        r = lab.get(grow["row"])
        tag = f"   =>  OUR: {r['class']}/{r.get('section', '?')}" if r else ""
        L.append(f"{grow['row']:>4} | " + "  ".join(parts) + tag)
    return "\n".join(L)


DIAGNOSIS_PROMPT = """You are an expert auditor of commercial real estate T12 (trailing-12-month) income statements.

Our automated pipeline parsed this sheet, classified every row (METADATA / SECTION_HEADER / SUBSECTION_HEADER / DATA / SUBSECTION_SUBTOTAL / SECTION_SUBTOTAL / COMPUTED_METRIC), tagged each row's section (revenue / expense / capex), and then its NOI check FAILED: the bottom-up NOI (sum of the rows WE labeled as revenue/expense DATA) does not match the vendor's reported NOI.

Decide the ROOT CAUSE, exactly one of:
- CLASSIFICATION_PROBLEM — WE mislabeled one or more rows, so the bottom-up sum is wrong. Common cases: a subtotal row we labeled DATA (double-counts its children); a real line item we labeled a subtotal (under-counts); a wrong section boundary. The vendor's own totals are self-consistent. Return EVERY mislabeled row you can find — deep hierarchies usually have SEVERAL nested subtotal rows all wrongly labeled DATA (e.g. multiple rollups such as 'Total Rental Inc.', 'Total Income', or code-only totals such as those ending ...099/...999); list ALL of them in problem_rows, each with the class we gave and the correct class (EXACTLY one of the seven class names).
- DATA_PROBLEM — the vendor's OWN reported totals are internally inconsistent (e.g. their stated NOI is not their Total Income minus Total Expense), so NO relabeling can make it reconcile. Return which total is off and by how much.
- UNCERTAIN — the data does not let you decide.

KEY DECISION RULE — apply this first, using the per-section figures already given in the discrepancy:
- If our REVENUE total differs from the vendor's revenue total, OR our EXPENSE total differs from the vendor's expense total, then WE summed the wrong rows in that section -> CLASSIFICATION_PROBLEM. The mislabeled row is almost always in that section and its value equals the delta (a subtotal we labeled DATA over-counts; a line item we labeled a subtotal under-counts).
- If our revenue total MATCHES the vendor's revenue total AND our expense total MATCHES the vendor's expense total, then our NOI (revenue minus expense) is arithmetically correct by definition. Any remaining NOI mismatch then means the VENDOR's reported NOI does not equal their own revenue minus expense -> DATA_PROBLEM. Report the vendor's NOI, their revenue minus expense, and the difference. Do NOT invent a "missing row" in this case.

You are given our detected structure, the exact arithmetic discrepancy, and the FULL raw grid with OUR label on each row. Do NOT recompute long column sums yourself — reason from the row descriptions, our labels, and the discrepancy figures already given.

DETECTED STRUCTURE:
{structure}

NOI DISCREPANCY:
{discrepancy}

RAW GRID WITH OUR LABELS:
{grid_text}
"""


def run_diagnosis_agent(classified, grid, final_map, noi_res):
    """Robust: retries once, and on any parse failure returns an UNCERTAIN result
    instead of raising, so a malformed LLM response can't crash the pipeline."""
    llm = make_llm(agent_name=DIAGNOSIS_AGENT)
    structured = llm.with_structured_output(DiagnosisResult)
    prompt = PromptTemplate(input_variables=["structure", "discrepancy", "grid_text"],
                            template=DIAGNOSIS_PROMPT)
    chain = prompt | structured
    inputs = {"structure":   render_structure_summary(final_map),
              "discrepancy": render_discrepancy(noi_res),
              "grid_text":   render_grid_with_labels(grid, classified, final_map)}
    last_err = None
    for _ in range(2):
        try:
            res = chain.invoke(inputs)
            res.problem_rows = res.problem_rows or []
            return res
        except Exception as e:
            last_err = e
    return DiagnosisResult(verdict="UNCERTAIN", problem_rows=[],
                           user_message="Diagnosis response could not be parsed; needs human review.",
                           reasoning=f"structured-output error: {str(last_err)[:150]}")
