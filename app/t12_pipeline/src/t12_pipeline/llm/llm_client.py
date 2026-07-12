import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic

from t12_pipeline.config.agent_llm_config import DEFAULT_AGENT_NAME, get_agent_llm_config

# Always load the shared app-level .env (app/.env), regardless of cwd.
# parents: [0]=llm [1]=t12_pipeline [2]=src [3]=app/t12_pipeline [4]=app
load_dotenv(Path(__file__).resolve().parents[4] / ".env")


def make_llm(
    agent_name: str = DEFAULT_AGENT_NAME,
    provider: str | None = None,              # "openai" | "lmstudio" | "gemini" | "anthropic"
    model: str | None = None,
    temperature: float | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
):
    agent_config = get_agent_llm_config(agent_name)
    agent_provider = str(agent_config["provider"]).lower().strip()

    provider = (provider or str(agent_config["provider"])).lower().strip()

    # Inherit the agent's model / api_key_env ONLY when the requested provider
    # matches the agent's provider. Otherwise (e.g. provider="anthropic" while the
    # default agent is OpenAI) leave them None so each provider branch below fills
    # its own defaults — this stops an OpenAI model/key from leaking into a
    # Claude/Gemini call.
    same_provider = provider == agent_provider
    model = model or (agent_config.get("model") if same_provider else None)  # type: ignore[assignment]
    temperature = temperature if temperature is not None else float(agent_config.get("temperature", 0.15))
    api_key_env = api_key_env or (agent_config.get("api_key_env") if same_provider else None)  # type: ignore[assignment]

    # -------------------------
    # OpenAI (Cloud)
    # -------------------------
    if provider == "openai":
        model = model or os.getenv("OPENAI_MODEL", "gpt-5-nano")
        api_key_env = api_key_env or "OPENAI_API_KEY_AI_MAPPING"
        api_key = os.getenv(api_key_env)

        if not api_key:
            raise ValueError(f"{api_key_env} is missing")

        return ChatOpenAI(
            model=model,
            api_key=api_key, # type: ignore
            temperature=temperature,
        )

    # -------------------------
    # LM Studio (Local, OpenAI-compatible)
    # -------------------------
    if provider == "lmstudio":
        base_url = base_url or os.getenv(
            "LMSTUDIO_BASE_URL", "http://localhost:1234/v1"
        )
        model = model or os.getenv(
            "LMSTUDIO_MODEL", "qwen/qwen2.5-coder-14b"
        )
        api_key = os.getenv("LMSTUDIO_API_KEY", "lm-studio")  # dummy key

        return ChatOpenAI(
            model=model,
            api_key=api_key, #type: ignore
            base_url=base_url,
            temperature=temperature,
        )

    # -------------------------
    # Gemini (Google)
    # -------------------------
    if provider == "gemini":
        model = model or os.getenv(
            "GEMINI_MODEL", "gemini-2.5-flash-lite"
        )
        api_key_env = api_key_env or "GOOGLE_API_KEY"
        api_key = os.getenv(api_key_env)

        if not api_key:
            raise ValueError(f"{api_key_env} is missing")

        return ChatGoogleGenerativeAI(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )

    # -------------------------
    # Anthropic (Claude)
    # -------------------------
    if provider in ("anthropic", "claude"):
        model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        api_key_env = api_key_env or "CLAUDE_API_KEY"
        api_key = os.getenv(api_key_env)

        if not api_key:
            raise ValueError(f"{api_key_env} is missing")

        # The Claude 5 family deprecated `temperature` (the API 400s if it's sent),
        # so we don't forward it. These models are low-variance by default, and our
        # downstream arithmetic checks catch any drift.
        return ChatAnthropic(
            model=model,       # type: ignore
            api_key=api_key,   # type: ignore
            max_tokens=8192,   # Claude requires an explicit cap; large enough for our structured JSON
        )

    raise ValueError(
        f"Unknown provider: {provider}. Use 'openai', 'lmstudio', 'gemini', or 'anthropic'."
    )


# -------------------------
# Example usage
# -------------------------
if __name__ == "__main__":

    # llm_local = make_llm(
    #     provider="lmstudio",
    #     model="qwen/qwen2.5-coder-14b",
    # )
    # print(llm_local.invoke("Hi From LmStudio, how are you?").content)

    # llm_gemini = make_llm(
    #     provider="gemini",
    #     model="gemini-2.5-flash-lite",
    # )
    # print(llm_gemini.invoke("Hi from Gemini").content)

    llm = make_llm()
    print(llm.invoke("gree me in one sentence?").content)


    # llm_openai = make_llm(provider="openai")
    # print(llm_openai.invoke("Hi from OpenAI").content)


##############################################################
##############################################################
##############################################################

# # # gemini_client.py
# # import os
# # from langchain_google_genai import ChatGoogleGenerativeAI

# # from dotenv import load_dotenv
# # load_dotenv()

# # GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY2")
# # def make_llm(model: str = "gemini-2.5-flash-lite", temperature: float = 0.15):
# #     return ChatGoogleGenerativeAI(
# #         model=model,
# #         api_key=GOOGLE_API_KEY,
# #         temperature=temperature,
# #     )


# # # GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY4")
# # # def make_llm(model: str = "gemini-2.5-pro", temperature: float = 0.15):
# # #     return ChatGoogleGenerativeAI(
# # #         model=model,
# # #         api_key=GOOGLE_API_KEY,
# # #         temperature=temperature,
# # #     )

# # if __name__ == "__main__":
# #     # Example usage:
# #     llm = make_llm()
# #     res = llm.invoke("Hi").content
# #     print(res)


# # openai_client.py
# import os
# from dotenv import load_dotenv
# from langchain_openai import ChatOpenAI

# load_dotenv()

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# # def make_llm(
# #     model: str = "gpt-5.2",
# #     temperature: float = 0.15
# # ):
# #     return ChatOpenAI(
# #         model=model,
# #         api_key=OPENAI_API_KEY,
# #         temperature=temperature,
# #     )

# def make_llm(
#     model: str = "gpt-5-nano",
#     temperature: float = 0.15
# ):
#     return ChatOpenAI(
#         model=model,
#         api_key=OPENAI_API_KEY, # type: ignore
#         temperature=temperature,
#     )

# # def make_llm(
# #     model: str = "gpt-4o-mini",
# #     temperature: float = 0.15
# # ):
# #     return ChatOpenAI(
# #         model=model,
# #         api_key=OPENAI_API_KEY,
# #         temperature=temperature,
# #     )

# if __name__ == "__main__":
#     # Example usage
#     llm = make_llm()
#     res = llm.invoke("Hi").content
#     print(res)
