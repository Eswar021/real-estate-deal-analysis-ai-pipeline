import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from config.agent_llm_config import MAPPING_AI_AGENT
from llm_client import make_llm


if __name__ == "__main__":
    llm = make_llm(agent_name=MAPPING_AI_AGENT)
    print(llm.invoke("Hi from the configured mapping AI agent.").content)
