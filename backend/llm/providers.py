# backend/llm/providers.py
# Picks who writes conversation lines and plans (config.CONVERSATION_LLM):
# the templates in backend/sim/speech.py, or Claude with the template as
# a per-call fallback — one failed call costs one dull line, never a
# stuck village.
import logging

from backend.config import CONVERSATION_LLM
from backend.sim import speech

log = logging.getLogger(__name__)


def conversation_functions():
    """(speaker, planner): view -> turn, view -> plan."""
    if CONVERSATION_LLM != "claude":
        return speech.template_turn, speech.template_replan
    from backend.llm import claude   # only needs the SDK when actually used
    return (_with_fallback(claude.claude_turn, speech.template_turn, claude.ClaudeUnavailable),
            _with_fallback(claude.claude_plan, speech.template_replan, claude.ClaudeUnavailable))


def _with_fallback(primary, backup, unavailable):
    def call(view):
        try:
            return primary(view)
        except unavailable as exc:
            log.warning("%s fell back to the template: %s", primary.__name__, exc)
            return backup(view)
    call.__name__ = primary.__name__
    return call
