# backend/sim/decider.py
# Decides what an agent does this tick.
# Primary path: ask the LLM for a structured JSON action.
# Fallback path: a simple hour-based routine, so the simulation keeps
# running even with no LLM server up (e.g. secondary machine powered off).
import json
import re

from backend.llm.client import chat, LLMUnavailable
from backend.sim.actions import ActionType

SYSTEM_PROMPT = """You are role-playing a villager in a medieval village simulation.
Decide the villager's next action for this five-minute tick.

Respond with ONLY a JSON object, no other text:
{"action": "MOVE|WORK|TALK|TRADE|REST|OBSERVE", "target": "<building name or villager name or null>", "dialogue": "<one short sentence if TALK, else null>"}

Rules:
- MOVE target must be one of the buildings listed.
- TALK target must be a villager in the same place; include a short in-character dialogue line.
- WORK only makes sense at your workplace.
- Villagers sleep at night (REST) and work during the day."""


def decide(agent, world_context: dict) -> dict:
    """Return {"action": ActionType, "target": str|None, "dialogue": str|None}."""
    try:
        raw = chat(SYSTEM_PROMPT, _build_user_prompt(agent, world_context))
        decision = _parse_decision(raw)
        if decision:
            return decision
    except LLMUnavailable:
        pass
    return _rule_based(agent, world_context)


def _build_user_prompt(agent, ctx: dict) -> str:
    nearby = ", ".join(ctx["nearby_agents"]) or "nobody"
    return (
        f"You are {agent.name}, a {agent.age}-year-old {agent.job}.\n"
        f"Personality: {agent.personality}\n"
        f"Current time: day {ctx['day']}, {ctx['hour']:02d}:{ctx['minute']:02d}.\n"
        f"You are at: {agent.location}. Your workplace: {agent.workplace}.\n"
        f"Your wealth: {agent.wealth} copper. Inventory: {json.dumps(agent.inventory)}.\n"
        f"Villagers at the same place: {nearby}.\n"
        f"Buildings: {', '.join(ctx['buildings'])}.\n"
        f"What do you do this hour?"
    )


def _parse_decision(raw: str):
    """Extract the first JSON object from the model output, tolerantly."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        action = ActionType(data["action"].upper())
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
    return {
        "action": action,
        "target": data.get("target"),
        "dialogue": data.get("dialogue"),
    }


def _rule_based(agent, ctx: dict) -> dict:
    """Deterministic daily routine used when no LLM is reachable."""
    hour = ctx["hour"]
    if hour < 6 or hour >= 22:
        return {"action": ActionType.REST, "target": None, "dialogue": None}
    if 6 <= hour < 18:
        if agent.location != agent.workplace:
            return {"action": ActionType.MOVE, "target": agent.workplace, "dialogue": None}
        return {"action": ActionType.WORK, "target": None, "dialogue": None}
    # Evening: gather at the inn and chat.
    if agent.location != "Inn":
        return {"action": ActionType.MOVE, "target": "Inn", "dialogue": None}
    if ctx["nearby_agents"]:
        return {
            "action": ActionType.TALK,
            "target": ctx["nearby_agents"][0],
            "dialogue": "Good evening! How was your day?",
        }
    return {"action": ActionType.OBSERVE, "target": None, "dialogue": None}
