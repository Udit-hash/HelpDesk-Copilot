"""LLM setup using LangChain.

ChatOpenAI talks to any OpenAI-compatible API, so the same code works with Groq
(default), OpenAI, Gemini's OpenAI endpoint, or a local model server.
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from . import config


class LLMError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(config.LLM_API_KEY)


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
        temperature=0.1,
        timeout=60,
        max_retries=1,
    )
