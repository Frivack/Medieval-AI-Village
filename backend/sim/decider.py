# backend/sim/decider.py
# Decides what an agent does this tick.
# Primary path: ask the LLM for a structured JSON action.
# Fallback path: a simple hour-based routine, so the simulation keeps
# running even with no LLM server up (e.g. secondary machine powered off).
import json
import re

from backend.config import MEMORIES_IN_PROMPT
from backend.llm.client import chat, LLMUnavailable
from backend.memory.store import memory_store
from backend.sim.actions import ActionType
from backend.sim.clock import format_clock

SYSTEM_PROMPT = """You are role-playing a villager in a medieval village simulation.
Decide the villager's next action for this five-minute tick.

Respond with ONLY a JSON object, no other text:
{"action": "MOVE|WORK|TALK|TRADE|REST|OBSERVE", "target": "<building name or villager name or null>", "dialogue": "<one short sentence if TALK, else null>", "item": "<item name if TRADE, else null>", "quantity": <number if TRADE, else null>}

Rules:
- MOVE target must be one of the buildings listed.
- TALK target must be a villager in the same place; include a short in-character dialogue line.
- TRADE means you BUY item x quantity from a villager in the same place; you must be able to afford it.
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
    memories = _memory_lines(agent, ctx)
    memory_block = ("Your memories:\n" + "\n".join(memories) + "\n") if memories else ""
    return (
        f"You are {agent.name}, a {agent.age}-year-old {agent.job}.\n"
        f"Personality: {agent.personality}\n"
        f"Current time: day {ctx['day']}, {ctx['hour']:02d}:{ctx['minute']:02d}.\n"
        f"You are at: {agent.location}. Your workplace: {agent.workplace}.\n"
        f"Your wealth: {agent.wealth} copper. Inventory: {json.dumps(agent.inventory)}.\n"
        f"Villagers at the same place: {nearby}.\n"
        f"Buildings: {', '.join(ctx['buildings'])}.\n"
        f"{memory_block}"
        f"What do you do right now?"
    )


# One importance point outweighs 72 ticks (6 in-game hours) of recency —
# a trade (importance 3) stays in the prompt about half a day longer
# than small talk (importance 2) of the same age.
_TICKS_PER_IMPORTANCE = 72


def _memory_lines(agent, ctx: dict) -> list[str]:
    """Select memories for the prompt: recency + importance scoring
    (mini Generative Agents), deduplicated, shown in time order. The
    vector store (when available) contributes semantically relevant
    older memories on top."""
    now = ctx["tick"]
    # Dedupe identical texts keeping the newest occurrence — one evening
    # of repeated greetings would otherwise fill every prompt slot.
    newest = {}
    for m in (agent.short_term_memory or []):
        newest[m["text"]] = m
    scored = sorted(
        newest.values(),
        key=lambda m: m.get("importance", 1) * _TICKS_PER_IMPORTANCE - (now - m["tick"]),
        reverse=True,
    )[:MEMORIES_IN_PROMPT]
    scored.sort(key=lambda m: m["tick"])
    lines = [f"- [{format_clock(m['tick'])}] {m['text']}" for m in scored]

    if memory_store.enabled and scored:
        situation = (
            f"{ctx['hour']:02d}:{ctx['minute']:02d} at {agent.location}, "
            f"nearby: {', '.join(ctx['nearby_agents']) or 'nobody'}"
        )
        seen = {m["text"] for m in scored}
        older = [t for t in memory_store.query(agent.id, situation, k=3)
                 if t not in seen]
        lines += [f"- (earlier) {t}" for t in older]
    return lines


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
        "item": data.get("item"),
        "quantity": data.get("quantity"),
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
    # Evening: gather at the inn, buy a meal, and chat.
    if agent.location != "Inn":
        return {"action": ActionType.MOVE, "target": "Inn", "dialogue": None}
    # Once per hour (minute-0 tick), buy a meal from the innkeeper. Four
    # evening hours x 3 guests = 12 meals/day, which exactly matches what
    # the innkeeper's WORK produces (1 food/hour x 12h).
    if (agent.job != "Innkeeper" and ctx["minute"] == 0
            and "Margaret" in ctx["nearby_agents"]):
        return {"action": ActionType.TRADE, "target": "Margaret",
                "item": "food", "quantity": 1, "dialogue": None}
    if ctx["nearby_agents"]:
        return {
            "action": ActionType.TALK,
            "target": ctx["nearby_agents"][0],
            "dialogue": "Good evening! How was your day?",
        }
    return {"action": ActionType.OBSERVE, "target": None, "dialogue": None}
