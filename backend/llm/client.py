# backend/llm/client.py
# Thin wrapper over any OpenAI-compatible /chat/completions endpoint.
# LM Studio, llama.cpp server and Groq all speak this protocol, so moving
# between them is just a base-URL change (backend/config.py).
import httpx

from backend.config import (
    LLM_BASE_URL, LLM_MODEL, LLM_API_KEY,
    LLM_CONNECT_TIMEOUT, LLM_READ_TIMEOUT,
)


class LLMUnavailable(Exception):
    """Raised when the LLM server can't be reached or errors out."""


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
    }
    timeout = httpx.Timeout(LLM_READ_TIMEOUT, connect=LLM_CONNECT_TIMEOUT)
    try:
        response = httpx.post(
            f"{LLM_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise LLMUnavailable(str(exc)) from exc
