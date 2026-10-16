# backend/llm/claude.py
# Claude as a conversation speaker and as a schedule planner — the same
# signatures as the templates in backend/sim/speech.py (view -> turn,
# view -> plan), selected by backend/llm/providers.py.
#
# Official anthropic SDK, structured outputs (the reply is JSON matching
# prompts.TURN_SCHEMA / PLAN_SCHEMA), the fixed system prompt marked for
# prompt caching, the cheapest thinking setting each model allows, and a
# small token budget. On Opus/Sonnet a refused request is first re-run by
# the API itself on a fallback model. Every remaining failure — API error,
# timeout, refusal, daily limit, unparseable reply — raises
# ClaudeUnavailable; the caller then uses the template for that one line
# or plan.
import json
import logging

import anthropic

from backend.config import (CLAUDE_EFFORT, CLAUDE_MODEL, CLAUDE_TIMEOUT_SECONDS,
                            LLM_DAILY_CALL_LIMIT)
from backend.llm import prompts, usage

log = logging.getLogger(__name__)

# Thinking per model (claude-api skill): Haiku 5.5 may turn it off at
# effort <= high; Sonnet 5.5 turns it off with "between_tools"; Opus 5.5
# can't turn it off — omit the parameter and let low effort keep it short.
_THINKING = {
    "claude-haiku-5-5": {"type": "disabled"},
    "claude-sonnet-5-5": {"type": "between_tools"},
}
# Server-side refusal fallback (claude-api skill: ship it from day one on
# Opus/Sonnet 5.5): if a safety classifier wrongly declines a request, the
# API re-runs it on the model Anthropic recommends for that refusal
# category, inside the same call. Haiku 5.5 has no server-side fallback.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_SERVER_FALLBACK = {"claude-opus-5-5", "claude-sonnet-5-5"}
TURN_MAX_TOKENS = 1024     # a line + a small JSON object, with room for brief thinking
PLAN_MAX_TOKENS = 2048


class ClaudeUnavailable(Exception):
    """No usable answer from Claude this time; use the template instead."""


_client = None


def _get_client():
    global _client
    if _client is None:
        # Reads ANTHROPIC_API_KEY (loaded from .env by backend.config).
        # One retry: a tick shouldn't wait out the SDK's default two.
        _client = anthropic.Anthropic(timeout=CLAUDE_TIMEOUT_SECONDS, max_retries=1)
    return _client


def _ask(system: str, user: str, schema: dict, max_tokens: int, model: str = None) -> dict:
    model = model or CLAUDE_MODEL
    if usage.calls_today() >= LLM_DAILY_CALL_LIMIT:
        raise ClaudeUnavailable(f"daily limit of {LLM_DAILY_CALL_LIMIT} calls reached")
    request = {
        "model": model,
        "max_tokens": max_tokens,
        # Same text on every call, so the API can serve it from the cache.
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": CLAUDE_EFFORT,
                          "format": {"type": "json_schema", "schema": schema}},
    }
    if model in _THINKING:
        request["thinking"] = _THINKING[model]
    client = _get_client()
    try:
        if model in _SERVER_FALLBACK:
            response = client.beta.messages.create(**request, betas=[_FALLBACK_BETA],
                                                   fallbacks="default")
        else:
            response = client.messages.create(**request)
    except anthropic.APIError as exc:          # connection, timeout, 4xx/5xx, spend limit
        usage.record_failure()
        raise ClaudeUnavailable(f"{type(exc).__name__}: {exc}") from exc
    # A rescued request reports the fallback model; price it as ours if
    # it's not one we know (rare, and the estimate only needs to be close).
    served = getattr(response, "model", None)
    usage.record(served if served in usage.PRICES else model, response.usage)
    if response.stop_reason == "refusal":
        raise ClaudeUnavailable("the model declined")
    if response.stop_reason == "max_tokens":
        raise ClaudeUnavailable("reply cut off at max_tokens")
    text = next((b.text for b in response.content if b.type == "text"), None)
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ClaudeUnavailable(f"unparseable reply: {text!r:.80}") from exc
    if not isinstance(data, dict):
        raise ClaudeUnavailable("reply is not a JSON object")
    return data


def claude_turn(view: dict) -> dict:
    data = _ask(prompts.SPEAKER_SYSTEM, prompts.speaker_prompt(view),
                prompts.TURN_SCHEMA, TURN_MAX_TOKENS)
    return prompts.turn_from_json(data, view)


def claude_plan(view: dict) -> dict:
    # Waking up has its own prompt and a schema with nothing but edits.
    wake = view["event"] == "wake_up"
    data = _ask(prompts.WAKE_SYSTEM if wake else prompts.PLANNER_SYSTEM, prompts.plan_prompt(view),
                prompts.WAKE_SCHEMA if wake else prompts.PLAN_SCHEMA, PLAN_MAX_TOKENS)
    return prompts.plan_from_json(data)
