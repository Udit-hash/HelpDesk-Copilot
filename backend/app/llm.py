"""Thin client for any OpenAI-compatible chat completions API (Groq, OpenAI, Gemini, ...)."""
import httpx

from . import config


class LLMError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(config.LLM_API_KEY)


def chat(messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.1) -> dict:
    """Send a chat request and return the assistant message (dict with content / tool_calls)."""
    payload = {"model": config.LLM_MODEL, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    try:
        resp = httpx.post(
            f"{config.LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            json=payload,
            timeout=60,
        )
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach the LLM API: {e}") from e
    if resp.status_code != 200:
        raise LLMError(f"LLM API returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]
