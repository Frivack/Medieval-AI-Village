# backend/sim/negotiation.py
# TRADE v2: single-tick price negotiation, layered on the v1 settlement
# core in tick_engine._do_trade. At most two LLM calls per trade:
#
#   1. seller reacts to the base-price offer: accept / counter / refuse
#   2. if countered, buyer reacts to the counter: accept / refuse
#
# Counters are clamped to 70-130% of the base price so a hallucinating
# model can't wreck the economy. When no LLM is reachable (the
# deployment box, LM Studio off) the seller accepts the base price —
# which is exactly TRADE v1 — so the rule-based fallback keeps working.
import json
import re

from backend.llm.client import chat, LLMUnavailable
from backend.utils.currency import to_string

COUNTER_MIN = 0.7
COUNTER_MAX = 1.3
MEMORIES_IN_NEGOTIATION = 5

SELLER_SYSTEM = """You are role-playing a villager in a medieval village simulation.
A buyer wants to purchase goods from you. Decide how you respond to their offer.

Respond with ONLY a JSON object, no other text:
{"decision": "accept|counter|refuse", "price": <your total price in copper if counter, else null>, "line": "<one short in-character sentence>"}

Rules:
- "accept" sells at the offered price.
- "counter" proposes your own total price in copper; stay within 70%-130% of the offer.
- "refuse" declines the sale entirely.
- Stay in character; let your personality and memories guide the price."""

BUYER_SYSTEM = """You are role-playing a villager in a medieval village simulation.
You offered to buy goods and the seller made a counter-offer. Decide whether to take it.

Respond with ONLY a JSON object, no other text:
{"decision": "accept|refuse", "line": "<one short in-character sentence>"}"""


def negotiate(buyer, seller, item: str, quantity: int, base_total: int) -> dict:
    """Return {"outcome": "accept"|"refuse", "price": int, "dialogue": [str, ...]}.

    price is the agreed TOTAL in copper. dialogue holds the in-character
    lines exchanged (empty when the LLM was not involved).
    """
    try:
        raw = chat(SELLER_SYSTEM, _seller_prompt(buyer, seller, item, quantity, base_total))
        resp = _parse(raw, allowed={"accept", "counter", "refuse"})
    except LLMUnavailable:
        resp = None
    if resp is None:  # no LLM or unparseable output -> v1 behavior
        return {"outcome": "accept", "price": base_total, "dialogue": []}

    dialogue = [f"{seller.name}: {resp['line']}"] if resp["line"] else []

    if resp["decision"] == "accept":
        return {"outcome": "accept", "price": base_total, "dialogue": dialogue}
    if resp["decision"] == "refuse":
        return {"outcome": "refuse", "price": base_total, "dialogue": dialogue}

    counter = _clamp_counter(resp["price"], base_total)
    try:
        raw = chat(BUYER_SYSTEM, _buyer_prompt(buyer, seller, item, quantity,
                                               base_total, counter))
        resp2 = _parse(raw, allowed={"accept", "refuse"})
    except LLMUnavailable:
        resp2 = None
    if resp2 and resp2["line"]:
        dialogue.append(f"{buyer.name}: {resp2['line']}")

    # If the buyer's model failed to answer, take the (clamped, therefore
    # reasonable) counter rather than dropping the whole trade.
    if resp2 is None or resp2["decision"] == "accept":
        return {"outcome": "accept", "price": counter, "dialogue": dialogue}
    return {"outcome": "refuse", "price": counter, "dialogue": dialogue}


def _clamp_counter(price, base_total: int) -> int:
    try:
        price = int(price)
    except (TypeError, ValueError):
        return base_total
    low = max(1, int(base_total * COUNTER_MIN))
    high = max(1, int(base_total * COUNTER_MAX))
    return min(max(price, low), high)


def _relevant_memories(agent, partner_name: str, item: str) -> list[str]:
    """The agent's memories that mention this partner or this item —
    the context that makes 'you charged me 14c yesterday' possible."""
    hits = [m["text"] for m in (agent.short_term_memory or [])
            if partner_name in m["text"] or item in m["text"]]
    return hits[-MEMORIES_IN_NEGOTIATION:]


def _seller_prompt(buyer, seller, item, quantity, base_total) -> str:
    memories = _relevant_memories(seller, buyer.name, item)
    memory_block = ("Your relevant memories:\n" +
                    "\n".join(f"- {m}" for m in memories) + "\n") if memories else ""
    stock = (seller.inventory or {}).get(item, 0)
    return (
        f"You are {seller.name}, a {seller.age}-year-old {seller.job}.\n"
        f"Personality: {seller.personality}\n"
        f"Your wealth: {seller.wealth} copper. You have {stock} {item} in stock.\n"
        f"{buyer.name} offers to buy {quantity} {item} for {base_total} copper total "
        f"({to_string(base_total)}) — the usual market price.\n"
        f"{memory_block}"
        f"How do you respond?"
    )


def _buyer_prompt(buyer, seller, item, quantity, base_total, counter) -> str:
    memories = _relevant_memories(buyer, seller.name, item)
    memory_block = ("Your relevant memories:\n" +
                    "\n".join(f"- {m}" for m in memories) + "\n") if memories else ""
    return (
        f"You are {buyer.name}, a {buyer.age}-year-old {buyer.job}.\n"
        f"Personality: {buyer.personality}\n"
        f"Your wealth: {buyer.wealth} copper.\n"
        f"You offered {seller.name} {base_total} copper for {quantity} {item}; "
        f"they counter with {counter} copper total ({to_string(counter)}).\n"
        f"{memory_block}"
        f"Do you take the deal?"
    )


def _parse(raw: str, allowed: set[str]):
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        decision = str(data["decision"]).lower()
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
    if decision not in allowed:
        return None
    line = data.get("line")
    return {
        "decision": decision,
        "price": data.get("price"),
        "line": str(line).strip() if line else None,
    }
