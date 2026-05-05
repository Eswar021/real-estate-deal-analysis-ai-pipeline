import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


def make_llm(
    provider: str = "openai",                  # "openai" | "lmstudio" | "gemini"
    model: str | None = None,
    temperature: float = 0.15,
    base_url: str | None = None,
):
    provider = provider.lower().strip()

    # -------------------------
    # OpenAI (Cloud)
    # -------------------------
    if provider == "openai":
        model = model or os.getenv("OPENAI_MODEL", "gpt-5-nano")
        api_key = os.getenv("OPENAI_API_KEY_S_M_R")

        if not api_key:
            raise ValueError("OPENAI_API_KEY_S_M_R is missing")

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
        api_key = os.getenv("GOOGLE_API_KEY")

        if not api_key:
            raise ValueError("GOOGLE_API_KEY is missing")

        return ChatGoogleGenerativeAI(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown provider: {provider}. Use 'openai', 'lmstudio', or 'gemini'."
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

