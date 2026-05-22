from t12_pipeline.config.agent_llm_config import MAPPING_AI_AGENT
from t12_pipeline.llm.llm_client import make_llm


if __name__ == "__main__":
    llm = make_llm(agent_name=MAPPING_AI_AGENT)
    print(llm.invoke("Hi from the configured mapping AI agent.").content)
