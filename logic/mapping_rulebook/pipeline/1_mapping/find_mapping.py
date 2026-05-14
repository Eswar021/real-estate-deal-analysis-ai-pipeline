import json
import sys
import os
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate

# Add project root to sys.path so we can import config & llm
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.paths import (
    AUTO_MAPPED_DIR, 
    AI_MAPPED_DIR, 
    AI_MAPPING_LOGS_DIR
    )
from config.rulebook_runtime import get_active_rulebook_name, get_active_rulebook_path
from config.agent_llm_config import MAPPING_AI_AGENT
from llm.llm_client import make_llm

ACTIVE_RULEBOOK_PATH = get_active_rulebook_path()
ACTIVE_RULEBOOK_NAME = get_active_rulebook_name()

# ── Structured Output Schema ──
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

def load_rulebook_categories(rulebook_path=ACTIVE_RULEBOOK_PATH):
    """Returns a list of existing categories from the rulebook to use as context."""
    with open(rulebook_path, "r") as f:
        rulebook = json.load(f)
    # The keys of the rulebook are the canonical categories
    return list(rulebook.keys())

def get_context_for_section(section_context, rulebook_path=ACTIVE_RULEBOOK_PATH):
    """
    Returns an examples dictionary mapping category to an array of example descriptions.
    """
    with open(rulebook_path, "r") as f:
        rulebook = json.load(f)
    
    examples = {}
    count = 0
    for k, v in rulebook.items():
        if count >= 10: break
        if v:  # if it has mapped descriptions
            examples[k] = v[:3]  # take up to 3 examples per category
            count += 1
    return examples

def create_ai_mapping_pipeline():
    """Sets up the Langchain prompt and LLM pipeline."""
    
    # Provider / model selection is owned by llm/llm_client.py.
    llm = make_llm(agent_name=MAPPING_AI_AGENT)
    structured_llm = llm.with_structured_output(AISuggestedMapping)
    
    prompt_path = Path(__file__).parent / "prompt.txt"
    with open(prompt_path, "r") as f:
        template = f.read()
        
    prompt = PromptTemplate(
        input_variables=[
            "valid_categories", 
            "mapping_examples", 
            "item_to_map"
        ],
        template=template
    )
    
    return prompt, prompt | structured_llm

def run_ai_mapping(file_data, limit=None):
    """
    Takes a single file dictionary (from auto_mapped), finds unmapped records, 
    calls the AI pipeline for each one individually, and updates the dictionary in-place.
    Returns the updated dictionary.
    """
    categories = load_rulebook_categories()
    valid_categories_str = "\n".join([f"- {c}" for c in categories])
    mapping_examples = get_context_for_section("")

    print(f"Using rulebook ({ACTIVE_RULEBOOK_NAME}): {ACTIVE_RULEBOOK_PATH}")
    
    prompt_template, pipeline = create_ai_mapping_pipeline()
    
    processed_count = 0
    file_name = file_data.get("file", "Unknown File")
    
    run_logs = []
    
    for row in file_data.get("rows", []):
        if row.get("not_found") is True:
            description = row.get("description", "")
            section_context = row.get("section_context", "")
            values = row.get("values", [])
            
            print(f"\nProcessing row {row['row']} - '{description}' in '{section_context}'...")
            
            item_to_map_dict = {
                "file_name": file_name,
                "section_context": section_context,
                "description": description,
                "column_headers": file_data.get("column_headers", []),
                "monthly_values": values
            }
            
            inputs = {
                "valid_categories": valid_categories_str,
                "mapping_examples": json.dumps(mapping_examples, indent=2),
                "item_to_map": json.dumps(item_to_map_dict, indent=2)
            }
            
            raw_prompt = prompt_template.format(**inputs)
            
            log_entry = {
                "row": row['row'],
                "description": description,
                "llm_final_prompt": raw_prompt,
                "llm_raw_output": None
            }
            
            try:
                # Invoke pipeline
                result = pipeline.invoke(inputs)
                
                # Add AI suggestion to the row
                row["ai_suggested_mapping"] = result.suggested_category
                row["ai_confidence"] = result.confidence
                row["ai_reasoning"] = result.reasoning
                
                log_entry["llm_raw_output"] = result.model_dump()
                
                print(f"  -> Suggested: {result.suggested_category} ({result.confidence})")
                print(f"  -> Reason: {result.reasoning}")
                
            except Exception as e:
                print(f"  -> Error querying AI: {e}")
                row["ai_suggested_mapping"] = None
                row["ai_confidence"] = None
                row["ai_reasoning"] = str(e)
                log_entry["error"] = str(e)
            
            run_logs.append(log_entry)
            processed_count += 1
            
            if limit and processed_count >= limit:
                print(f"\nReached limit of {limit} records. Stopping for this file.")
                break

    # Save logs
    if run_logs:
        log_file_path = AI_MAPPING_LOGS_DIR / f"{Path(file_name).stem}_logs.json"
        with open(log_file_path, "w") as f:
            json.dump(run_logs, f, indent=2)
        print(f"\nSaved logs to {log_file_path}")

    return file_data

if __name__ == "__main__":

    # Manual single-file harness. Keep this simple while the stage is still
    # being iterated; batch orchestration can move to a dedicated runner later.
    file_path = AUTO_MAPPED_DIR / "Willows of Coventry T12 11-25.json"
    # file_path = AUTO_MAPPED_DIR / "Pointe Inverness T12 11-25.json"
    
    with open(file_path, "r") as fp:
        file_data = json.load(fp)

    updated_data = run_ai_mapping(file_data)

    out_path = AI_MAPPED_DIR / file_path.name

    with open(out_path, "w") as fp:
        json.dump(updated_data, fp, indent=2)
    print(f"Saved AI mapped results to {out_path}")


    # json_files = sorted(list(AUTO_MAPPED_DIR.glob("*.json")))
    # print(f"Found {len(json_files)} file(s) in {AUTO_MAPPED_DIR}")

    # for f in json_files:
    #     print(f"\n{'='*50}\nProcessing file: {f.name}\n{'='*50}")
    #     with open(f, "r") as fp:
    #         file_data = json.load(fp)
            
    #     # Test run: Process only the first 5 unmapped records to verify pipeline works
    #     updated_data = run_ai_mapping(file_data, limit=5)
        
    #     out_path = AI_MAPPED_DIR / f.name
    #     with open(out_path, "w") as fp:
    #         json.dump(updated_data, fp, indent=2)
    #     print(f"Saved AI mapped results to {out_path}")
