"""Which model each AI agent runs on, and which env var holds its key.

All three agents run on Anthropic against ONE key (CLAUDE_API_KEY) — the deployment supplies
its own. Model overrides are per-agent env vars (T12_MAPPING_MODEL / T12_STRUCTURE_MODEL /
T12_DIAGNOSIS_MODEL); llm_client still speaks openai/gemini/lmstudio, but no agent is wired to
them, so no other key is needed to run the pipeline.
"""
import os

MAPPING_AI_AGENT = "mapping_ai_agent"
STRUCTURE_AGENT  = "t12_structure_agent"
DIAGNOSIS_AGENT  = "t12_diagnosis_agent"
DEFAULT_AGENT_NAME = MAPPING_AI_AGENT

AGENT_LLM_CONFIGS: dict[str, dict[str, object]] = {
    MAPPING_AI_AGENT: {
        "provider": "anthropic",
        "model": os.environ.get("T12_MAPPING_MODEL", "claude-sonnet-5"),
        "temperature": 0,
        "api_key_env": "CLAUDE_API_KEY",
        "notes": "pipeline/mapping/find_mapping.py — categorizes the rows the rulebook missed. "
                 "Sonnet, not Opus: it's the highest-volume agent (one call per unmapped row, "
                 "15 workers) on a constrained pick-from-a-list task.",
    },
    STRUCTURE_AGENT: {
        "provider": "anthropic",
        "model": os.environ.get("T12_STRUCTURE_MODEL", "claude-opus-4-8"),
        "temperature": 0,
        "api_key_env": "CLAUDE_API_KEY",
        "notes": "pipeline/parsing/structure_agent.py — reads the raw grid → structure map (unknown formats). Runs on every unknown file.",
    },
    DIAGNOSIS_AGENT: {
        "provider": "anthropic",
        "model": os.environ.get("T12_DIAGNOSIS_MODEL", "claude-opus-4-8"),
        "temperature": 0,
        "api_key_env": "CLAUDE_API_KEY",
        "notes": "pipeline/parsing/diagnosis.py — NOI-failure diagnosis (fires only when NOI verification FAILS).",
    },
}


def get_agent_llm_config(agent_name: str = DEFAULT_AGENT_NAME) -> dict[str, object]:
    if agent_name not in AGENT_LLM_CONFIGS:
        valid = ", ".join(sorted(AGENT_LLM_CONFIGS))
        raise ValueError(f"Unknown LLM agent: {agent_name}. Use one of: {valid}")
    return AGENT_LLM_CONFIGS[agent_name]
