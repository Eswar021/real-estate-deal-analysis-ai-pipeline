"""
find_mapping.py — Stage 1d (AI fallback)

Processes all unmapped non-capex rows using the LLM and updates the
auto-mapped JSON in place. Capex rows are skipped — they are excluded
from NOI regardless of category.

Reads:
    manifest["l1"]["paths"]["auto_mapped_dir"]     (per-file JSON)
    manifest["rulebook"]                           (passed in directly)
    manifest["l1"]["ai"]                           (provider/model config)
    manifest["l1"]["paths"]["ai_mapping_logs_dir"] (passed in directly)

Writes:
    manifest["l1"]["paths"]["ai_mapped_dir"]       (per-file JSON)
    manifest["l1"]["paths"]["ai_mapping_logs_dir"] (prompt/response logs)

Calls an LLM (OpenAI via LangChain structured output).
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

from config.agent_llm_config import MAPPING_AI_AGENT
from config.rulebook_utils import get_rulebook_categories, get_rulebook_examples
from llm.llm_client import make_llm

# GPT-5-nano TPM limit is 200K. Each call is ~2,200 tokens input.
# 5 workers × ~4s per call ≈ 75 calls/min, staying safely under the cap.
MAX_WORKERS = 5
_RETRY_DELAYS = [1, 2, 4]  # seconds between retries on 429


# ── Structured Output Schema ──────────────────────────────────────────────────
class AISuggestedMapping(BaseModel):
    suggested_category: str = Field(
        description="The standardized chart of account category mapping for the given item. "
                    "Must be chosen from the provided existing canonical categories exactly as written."
    )
    confidence: str = Field(
        description="High, Medium, or Low depending on how confident you are in the mapping."
    )
    reasoning: str = Field(
        description="Brief reasoning for why this mapping was chosen."
    )


# ── Pipeline setup ────────────────────────────────────────────────────────────
def create_ai_mapping_pipeline():
    llm = make_llm(agent_name=MAPPING_AI_AGENT)
    structured_llm = llm.with_structured_output(AISuggestedMapping)

    prompt_path = Path(__file__).parent / "prompt.txt"
    with open(prompt_path, "r") as f:
        template = f.read()

    prompt = PromptTemplate(
        input_variables=["valid_categories", "mapping_examples", "item_to_map"],
        template=template,
    )
    return prompt, prompt | structured_llm


# ── Per-row worker (runs in thread pool) ─────────────────────────────────────
def _process_single_row(row, file_name, column_headers, valid_categories_str, mapping_examples_str, prompt_template, pipeline):
    item_to_map_dict = {
        "file_name": file_name,
        "section_context": row.get("section_context", ""),
        "section_path": row.get("section_path"),
        "statement_side": row.get("statement_side"),
        "description": row.get("description", ""),
        "column_headers": column_headers,
        "monthly_values": row.get("values", []),
        "mapping_source": row.get("mapping_source"),
        "client_review_note": row.get("client_review_note"),
        "unresolved_reason_type": row.get("unresolved_reason_type"),
        "historical_candidate_mappings": row.get("historical_candidate_mappings"),
        "historical_statement_sides": row.get("historical_statement_sides"),
        "historical_section_paths": row.get("historical_section_paths"),
    }

    inputs = {
        "valid_categories": valid_categories_str,
        "mapping_examples": mapping_examples_str,
        "item_to_map": json.dumps(item_to_map_dict, indent=2),
    }

    raw_prompt = prompt_template.format(**inputs)
    log_entry = {
        "row": row["row"],
        "description": row.get("description", ""),
        "llm_final_prompt": raw_prompt,
        "llm_raw_output": None,
    }

    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            result = pipeline.invoke(inputs)
            row["ai_suggested_mapping"] = result.suggested_category
            row["ai_confidence"] = result.confidence
            row["ai_reasoning"] = result.reasoning
            log_entry["llm_raw_output"] = result.model_dump()
            print(f"  row {row['row']}: '{row.get('description')}' -> {result.suggested_category} ({result.confidence})")
            break
        except Exception as e:
            if "429" in str(e) and attempt < len(_RETRY_DELAYS):
                print(f"  row {row['row']}: rate limited, retrying in {_RETRY_DELAYS[attempt]}s...")
                continue
            row["ai_suggested_mapping"] = None
            row["ai_confidence"] = None
            row["ai_reasoning"] = str(e)
            log_entry["error"] = str(e)
            print(f"  row {row['row']}: ERROR - {e}")
            break

    return log_entry


# ── Main entry point ──────────────────────────────────────────────────────────
def run_ai_mapping(file_data, rulebook, ai_mapping_logs_dir, limit=None):
    """
    Processes all unmapped non-capex rows in a file dict in parallel.
    Updates rows in-place and returns the updated file_data dict.
    """
    categories = get_rulebook_categories(rulebook)
    valid_categories_str = "\n".join([f"- {c}" for c in categories])
    mapping_examples_str = json.dumps(get_rulebook_examples(rulebook), indent=2)

    prompt_template, pipeline = create_ai_mapping_pipeline()

    file_name = file_data.get("file", "Unknown File")
    column_headers = file_data.get("column_headers", [])

    unmapped_rows = [
        row for row in file_data.get("rows", [])
        if row.get("not_found") is True and row.get("statement_side") != "capex"
    ]

    if limit:
        unmapped_rows = unmapped_rows[:limit]

    print(f"Processing {len(unmapped_rows)} unmapped rows for {file_name} ({MAX_WORKERS} workers)...")

    if not unmapped_rows:
        return file_data

    run_logs = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(
                _process_single_row,
                row, file_name, column_headers,
                valid_categories_str, mapping_examples_str,
                prompt_template, pipeline,
            ): row
            for row in unmapped_rows
        }
        for future in as_completed(futures):
            run_logs.append(future.result())

    if run_logs:
        log_file_path = Path(ai_mapping_logs_dir) / f"{Path(file_name).stem}_logs.json"
        with open(log_file_path, "w") as f:
            json.dump(run_logs, f, indent=2)
        print(f"Saved logs to {log_file_path}")

    return file_data


if __name__ == "__main__":
    from config.paths import MANIFEST_PATH

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"No manifest at {MANIFEST_PATH}. Run Stage 0 first.")

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    rulebook = manifest["rulebook"]
    auto_mapped_dir = Path(manifest["l1"]["paths"]["auto_mapped_dir"])
    ai_mapped_dir = Path(manifest["l1"]["paths"]["ai_mapped_dir"])
    ai_mapping_logs_dir = Path(manifest["l1"]["paths"]["ai_mapping_logs_dir"])

    file_path = auto_mapped_dir / "Willows of Coventry T12 11-25.json"

    with open(file_path, "r") as fp:
        file_data = json.load(fp)

    updated_data = run_ai_mapping(file_data, rulebook, ai_mapping_logs_dir)

    out_path = ai_mapped_dir / file_path.name
    with open(out_path, "w") as fp:
        json.dump(updated_data, fp, indent=2)
    print(f"Saved AI mapped results to {out_path}")
