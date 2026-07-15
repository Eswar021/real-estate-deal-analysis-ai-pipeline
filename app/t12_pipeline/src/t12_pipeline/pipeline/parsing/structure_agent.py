"""Module 8a — AI structure-map agent (unknown formats).

Reads the raw grid and returns a full StructureMap (columns, code style, boundaries,
subsection hierarchy). The AI map is trusted; the arithmetic validates it downstream.
Ported verbatim from notebook Module 8a — model selection now goes through
`agent_llm_config` (STRUCTURE_AGENT → Claude Opus).
"""
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from openpyxl.utils import column_index_from_string, get_column_letter

from t12_pipeline.llm.llm_client import make_llm
from t12_pipeline.config.agent_llm_config import STRUCTURE_AGENT
from .cell_grid import grid_row_map, gvalue


def render_grid_for_agent(grid):
    """Fully-raw text view: each row 'row | COL=value  COL=value ...'.
    Text keeps its leading spaces; '*' marks bold; numbers rounded. No collapsing,
    no annotation — a capable model reads the raw grid directly."""
    L = [f"Sheet '{grid['sheet']}': used range rows 1-{grid['max_row']}, cols A-{get_column_letter(grid['max_col'])}."]
    if grid["merged_ranges"]:
        L.append(f"Merged cell ranges: {', '.join(grid['merged_ranges'])}")
    L.append("Each line below is one row: row_number | COL=cell_value  (text keeps its leading spaces; * = bold; numbers rounded).")
    L.append("")
    for grow in grid["rows"]:
        parts = []
        for c, cell in sorted(grow["cells"].items()):
            v = cell["value"]
            if v is None:
                continue
            star = "*" if cell["bold"] else ""
            v = round(v, 2) if isinstance(v, (int, float)) else repr(v)
            parts.append(f"{cell['letter']}{star}={v}")
        if parts:
            L.append(f"{grow['row']:>4} | " + "  ".join(parts))
    return "\n".join(L)


class Subsection(BaseModel):
    name: str = Field(description="the sub-group label as it reads in the sheet, e.g. 'Rental Income', 'Concessions', 'Payroll', 'Utilities'.")
    header_row: int | None = Field(description="the row where this sub-group STARTS — its header/label row, or its first line-item row if there is no separate header. Used to bound the sub-group for arithmetic checking.")
    subtotal_row: int = Field(description="the row holding this sub-group's subtotal (its value = the sum of the sub-group's line items).")


class StructureMap(BaseModel):
    # Layout — verify against the grid and correct if wrong
    description_columns: list[str] = Field(description="EVERY column letter that can hold an account description, left to right. In hierarchical/merged layouts a row's depth is shown by which column its text starts in — list all such columns.")
    code_column: str | None = Field(description="Column letter of a DEDICATED code column (codes only, separate from descriptions). If codes are embedded as a prefix inside the description text, set this to null.")
    code_embedded_in_description: bool = Field(description="True if account codes are a prefix inside the description text (e.g. '5120.0000 Rental Income'); False if codes have their own column or there are no codes.")
    code_pattern: str | None = Field(description="The code style, e.g. 'dot 5120.0000', 'colon 4010:', or null if there are no codes.")
    value_columns: list[str] = Field(description="ALL column letters holding the monthly numeric values (the full span).")
    month_header_row: int | None = Field(description="Row number of the month/period headers, or null.")
    data_start_row: int = Field(description="Row of the FIRST actual line-item (where the values begin).")
    # Sections — proposal, validated by arithmetic downstream
    revenue_end_row: int | None = Field(description="Row of the revenue grand total (Total Income / Effective Gross Income / Total Revenue).")
    expense_end_row: int | None = Field(description="Row of the operating-expense grand total (Total Operating Expenses / Total Expense).")
    noi_row: int | None = Field(description="Row of the Net Operating Income line.")
    subsections: list[Subsection] = Field(description="EVERY sub-group inside the revenue or expense sections that has its OWN subtotal row — at ALL nesting levels, top to bottom. Empty only if the sheet truly has no sub-group subtotals.")
    reasoning: str = Field(description="Brief explanation: note any field you CORRECTED from the candidate and why, and the labels used for the section rows.")


STRUCTURE_PROMPT = """You are an expert at reading commercial real estate T12 (trailing-12-month) income statements exported from various property-management systems.

You are given the raw cell grid of ONE worksheet. Identify its full structure so a deterministic parser can extract every row. Read the grid carefully — layouts vary widely (descriptions in one column or spread across several, different code styles, and extra columns such as Variance / % / budget that are NOT monthly periods).

Return the full structure:
- description_columns: EVERY column that can hold an account description, left to right (in hierarchical/merged layouts, depth is shown by which column the text starts in — list all of them).
- code_column / code_embedded_in_description / code_pattern: codes in their OWN dedicated column -> give that column, embedded=false. Codes as a prefix INSIDE the description text (e.g. '5120.0000 Rental Income') -> code_column=null, embedded=true. Describe the style in code_pattern.
- value_columns: ALL columns holding the monthly PERIOD numbers (the full span). Include a trailing total column (e.g. 'Total' / 'Adjusted Total') only if it is a genuine sum of the months; do NOT include derived columns such as 'Variance', '%', or a budget column.
- month_header_row: the row with the month/period headers.
- data_start_row: the first actual line-item row.
- revenue_end_row / expense_end_row / noi_row: the revenue grand total (Total Income / EGI), the operating-expense grand total (Total Operating Expenses), and the Net Operating Income line. These are a PROPOSAL — checked downstream against the arithmetic (revenue_total - expense_total ~= NOI at the last value column).
- subsections: EVERY sub-group inside the revenue or expense sections that has its OWN subtotal row, at ALL nesting levels, top to bottom. For each, give its name, its header/start row (header_row), and its subtotal row. A sub-group's subtotal is the row whose value equals the sum of that sub-group's line items. CRITICAL — a total row is NOT always obvious. It may be marked ANY of these ways, and you must include ALL of them: (a) the word 'Total' in its text; (b) BOLD 'repeated-name' text without the word 'Total' (e.g. a bold `Payroll` row summing the payroll lines); (c) ONLY by its account code with no descriptive text and no bold — e.g. a code ending in a round/rollup suffix such as ...099 or ...999 (like `41999-099 Total Rental Inc.` or `49999-999 Total Income`); or (d) simply by being the arithmetic sum of the plain detail rows above it. Deep hierarchies stack several of these; missing even one makes the downstream arithmetic double-count. When unsure whether a value row is a line-item or a total, check: does its value equal the sum of the rows above it? If yes, it is a total.

Use the exact row numbers and column letters shown in the grid.

Cell grid:
{grid_text}
"""


def build_structure_prompt(grid):
    """Return the EXACT prompt string that will be sent to the LLM (for inspection)."""
    return STRUCTURE_PROMPT.format(grid_text=render_grid_for_agent(grid))


def run_structure_agent(grid):
    """Invoke the structure agent (Claude Opus via agent_llm_config); returns a full
    StructureMap parsed from the raw grid."""
    llm = make_llm(agent_name=STRUCTURE_AGENT)
    structured_llm = llm.with_structured_output(StructureMap)
    prompt = PromptTemplate(input_variables=["grid_text"], template=STRUCTURE_PROMPT)
    chain = prompt | structured_llm
    return chain.invoke({"grid_text": render_grid_for_agent(grid)})


def _last_col_value(grid, row_num, last_col_letter):
    """Value at (row_num, last value column) — used by the arithmetic gate."""
    if row_num is None:
        return None
    grow = grid_row_map(grid).get(row_num)
    return gvalue(grow, column_index_from_string(last_col_letter)) if grow else None
