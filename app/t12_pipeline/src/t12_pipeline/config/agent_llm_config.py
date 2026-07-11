import os

MAPPING_AI_AGENT = "mapping_ai_agent"
STRUCTURE_AGENT  = "t12_structure_agent"
DIAGNOSIS_AGENT  = "t12_diagnosis_agent"
DEFAULT_AGENT_NAME = MAPPING_AI_AGENT

AGENT_LLM_CONFIGS: dict[str, dict[str, object]] = {
    MAPPING_AI_AGENT: {
        "provider": os.environ.get("OPENAI_PROVIDER", "openai"),
        "model": os.environ.get("OPENAI_MODEL", "gpt-5-nano"),
        "temperature": float(os.environ.get("OPENAI_TEMPERATURE", "0.15")),
        "api_key_env": "OPENAI_API_KEY_AI_MAPPING",
        "notes": "Used by pipeline/mapping/find_mapping.py for unmapped row categorization.",
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
