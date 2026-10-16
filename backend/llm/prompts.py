# backend/llm/prompts.py
# What the Claude speaker/planner reads, and the JSON shapes it answers in.
#
# English-first (CLAUDE.md §2). The system prompts and schemas never change
# between calls — so the API can cache them as a prefix — and everything
# that does change goes into the user message, rendered from the views in
# backend/sim/speech.py.
import json

from backend.config import BASE_DIR
from backend.sim import conversation, economy, schedule
from backend.sim.clock import format_clock
from backend.utils.currency import with_copper
from backend.world.map import village_map

ITEMS = sorted(economy.BASE_PRICES)
PLACES = list(village_map.buildings)
_ROSTER = json.loads((BASE_DIR / "data" / "agents.json").read_text(encoding="utf-8"))["agents"]
VILLAGERS = [a["name"] for a in _ROSTER]

_PRICE_LIST = ", ".join(f"{_item} {economy.BASE_PRICES[_item]}c" for _item in ITEMS)
_WORLD = f"""THE VILLAGE
Four buildings: {", ".join(PLACES)}. Four villagers: {"; ".join(f"{a['name']}, the {a['job'].lower()} (works at the {a['workplace']})" for a in _ROSTER)}.
How it runs: Thomas grows wheat, and needs farming tools to do it; tools wear out. Edmund makes farming tools. Gilbert the merchant buys wheat at the Farm in the morning and sells it at the Inn in the evening. Margaret cooks meals at the Inn from wheat. Everyone eats about three meals a day and carries a few. People work 06:00-18:00, spend the evening at the Inn and sleep at home 22:00-06:00, unless they plan otherwise.
Money: 1 gold (g) = 20 silver (s) = 200 copper (c), so 1 silver is 10 copper. Amounts are written with their copper total and, for several items, the price per item: "3s 4c (34c, 17c each)" — compare prices by those copper numbers. Usual prices per unit: {_PRICE_LIST}. A merchant usually buys at about {round(economy.WHOLESALE * 100)}% and sells at about {round(economy.RETAIL * 100)}% of these. Never use any other kind of coin."""

SPEAKER_SYSTEM = f"""You voice one villager in a small medieval village simulation, one line at a time, in a conversation with one other villager.

{_WORLD}

YOUR TURN — answer with JSON:
- line: what your villager says now. One or two short sentences, in character, plain spoken English. No narration, no stage directions, no quotation marks around it.
- offer: a deal you propose, or null. kind "buy" = you buy from them; kind "sell" = you sell to them. price is the TOTAL in copper for the whole quantity. Only buy what they sell here; only sell what you have to sell. A counter-offer is simply a new offer. The line should say it too.
- response: "accept" or "reject" to their pending offer; null if there is none. Accepting completes the deal at once: the goods and coin change hands right then. A deal marked as done is finished; offer it again only if you really want that much more.
- share: the id (like "n1") of one piece of news from your list that you tell them in this line, or null.
- end: true if this line ends the conversation (say goodbye in it).

Stay true to your personality, your needs and your memories. You only know what you are told here: not the other villager's money, stock or thoughts. Haggle if it suits you; refuse if it suits you. The whole conversation has at most 8 lines, so get to the point."""

_SCHEDULE = """The schedule is a list of time blocks with ids. "routine" blocks are the villager's usual day. Activities: WORK (only at your own workplace — it produces your goods), SOCIAL (spend time at a place, usually the Inn in the evening), SLEEP (at home), VISIT (go to a place; with a person = meeting them there). Walking takes time: up to about an hour between buildings."""

_OPS = f"""- change: false if the schedule should stay as it is — the usual answer. Change it only for a real reason this villager has: a promise or arrangement they made, something they need to buy or sell, something they heard, how they feel.
- ops: up to {schedule.MAX_OPS} edits, applied in order (empty if change is false):
  insert: day, from "HH:MM", to "HH:MM", do, at, with (a villager or null), why — the new block wins over whatever it overlaps.
  cancel: block (id) — an added block gives way to what it replaced; a cancelled routine block leaves free time.
  move: block (id), day, from, to — the same activity at a new time (what it replaced comes back).
  Use null for fields an edit doesn't need. Times on a {schedule.GRID_MINUTES}-minute grid, from now until the end of tomorrow. Every night must keep at least {schedule.SLEEP_FLOOR_MINUTES // 60} hours of sleep. Invalid edits are dropped."""

PLANNER_SYSTEM = f"""You plan the schedule of one villager in a small medieval village simulation, right after a conversation they had.

{_WORLD}

{_SCHEDULE}

ANSWER WITH JSON:
{_OPS}
- memory: one short first-person sentence worth remembering (a plan, a promise, an impression), or null.
- importance: 1 (routine), 2 (notable) or 3 (important) for that memory.
- affinity: how the conversation changed your feeling toward the other person, from -2 to 2 (0 if it didn't)."""

# Waking up only edits the schedule — like a tool call, it leaves no text
# behind (no memory, no affinity). The user's call, 2026-10-16.
WAKE_SYSTEM = f"""You manage the schedule of one villager in a small medieval village simulation at the moment they wake up. You don't speak and you write nothing down: your only output is edits to their schedule, the way a tool is called — or no edits at all.

{_WORLD}

{_SCHEDULE}

ANSWER WITH JSON:
{_OPS}"""

_NULL = {"type": "null"}


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, _NULL]}


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


TURN_SCHEMA = _object({
    "line": {"type": "string"},
    "offer": _nullable(_object({
        "kind": {"type": "string", "enum": ["buy", "sell"]},
        "item": {"type": "string", "enum": ITEMS},
        "quantity": {"type": "integer"},
        "price": {"type": "integer"},
    })),
    "response": _nullable({"type": "string", "enum": ["accept", "reject"]}),
    "share": _nullable({"type": "string"}),
    "end": {"type": "boolean"},
})

_OP_SCHEMA = _object({
    "op": {"type": "string", "enum": ["insert", "cancel", "move"]},
    "block": _nullable({"type": "string"}),
    "day": _nullable({"type": "integer"}),
    "from": _nullable({"type": "string"}),
    "to": _nullable({"type": "string"}),
    "do": _nullable({"type": "string", "enum": list(schedule.ACTIVITIES)}),
    "at": _nullable({"type": "string", "enum": PLACES}),
    "with": _nullable({"type": "string", "enum": VILLAGERS}),
    "why": _nullable({"type": "string"}),
})

PLAN_SCHEMA = _object({
    "change": {"type": "boolean"},
    "ops": {"type": "array", "items": _OP_SCHEMA},
    "memory": _nullable({"type": "string"}),
    "importance": {"type": "integer"},
    "affinity": {"type": "integer"},
})

WAKE_SCHEMA = _object({
    "change": {"type": "boolean"},
    "ops": {"type": "array", "items": _OP_SCHEMA},
})


# --- rendering the views ---------------------------------------------------

def speaker_prompt(v: dict) -> str:
    me, partner = v["me"], v["partner"]["name"]
    parts = [_who(me),
             f"It is {format_clock(v['time']['tick'])}. You are at the {v['place']}"
             + (f"; your schedule says {_doing(me['doing'])}." if me["doing"] else "."),
             _state(me),
             f"You are talking with {partner} the {v['partner']['job'].lower()}. "
             f"Toward them you feel: {_affinity(v['affinity'])}."]
    if v["i_started"] and not v["transcript"]:
        parts.append(f"You started this conversation: {_reason(v)}")
    elif not v["i_started"] and len(v["transcript"]) <= 1:
        parts.append(f"{partner} came over to talk to you.")
    if v["memories"]:
        parts.append("What you remember:\n" + "\n".join(v["memories"]))
    if v["news"]:
        parts.append(f"News you could tell {partner} (share at most one per line, by id):\n"
                     + "\n".join(f"[{n['id']}] {n['text']}" for n in v["news"]))
    parts.append(_goods(f"{partner} sells here", v["partner_sells"], "each")
                 or f"{partner} has nothing to sell here.")
    parts.append(_goods("You could sell them", v["i_sell"], "each, what they'd usually pay")
                 or "You have nothing to sell them here.")
    if v["could_buy"]:
        o = v["could_buy"]
        parts.append(f"You'd like to buy {o['quantity']} {o['item']} from them "
                     f"({with_copper(o['price'], o['quantity'])} at the usual price).")
    if v["deals"]:
        parts.append("Already done in this conversation (goods and coin have changed hands): "
                     + "; ".join(_deal(d) for d in v["deals"]) + ".")
    if v["pending_offer"]:
        parts.append(f"{partner}'s offer, waiting for your response: {_offer(v['pending_offer'], partner)}.")
    if v["transcript"]:
        parts.append("The conversation so far:\n" + "\n".join(
            f"{l['speaker']}{' (you)' if l['speaker'] == me['name'] else ''}: {l['text']}"
            + (f"  [{l['outcome']}]" if l.get("outcome") else "")
            for l in v["transcript"]))
    parts.append(f"{v['lines_left']} line(s) left in this conversation. Your turn, {me['name']}.")
    return "\n\n".join(parts)


def plan_prompt(v: dict) -> str:
    me = v["me"]
    parts = [_who(me)]
    if v["event"] == "wake_up":
        parts.append(f"It is {format_clock(v['time']['tick'])} and you just woke up at the {v['place']}.")
    else:
        partner = v["partner"]["name"]
        parts.append(f"It is {format_clock(v['time']['tick'])}. You just finished talking with "
                     f"{partner} at the {v['place']}. Before it you felt toward them: "
                     f"{_affinity(v['affinity'])}.")
        parts.append("The conversation:\n" + "\n".join(f"{l['speaker']}: {l['text']}"
                                                         for l in v["transcript"]))
        if v["deals"]:
            parts.append("Deals made: " + "; ".join(_deal(d) for d in v["deals"]))
    parts.append(_state(me))
    if v["memories"]:
        parts.append("What you remember:\n" + "\n".join(v["memories"]))
    parts.append("Your schedule from now:\n" + "\n".join(
        f"[{b['id']}] {b['from']} -> {b['to']}: {b['do']} at {b['at']}"
        + (f" with {b['with']}" if b["with"] else "") + (f" ({b['why']})" if b["why"] else "")
        + (" — routine" if b["routine"] else "")
        for b in v["schedule"]))
    parts.append(f"Does anything call for a change to {me['name']}'s schedule today?"
                 if v["event"] == "wake_up" else
                 "Did this conversation give you a reason to change your schedule?")
    return "\n\n".join(parts)


def turn_from_json(data: dict, v: dict) -> dict:
    """Model JSON -> engine turn. `share` comes back as an id; the engine
    needs the memory itself (unknown ids are dropped)."""
    share = next((n for n in v["news"] if n["id"] == data.get("share")), None)
    return {"line": data.get("line"), "end": data.get("end"), "offer": data.get("offer"),
            "response": data.get("response"), "share": share}


def plan_from_json(data: dict) -> dict:
    ops = [{k: val for k, val in op.items() if val is not None}
           for op in data.get("ops") or [] if isinstance(op, dict)]
    text = data.get("memory")
    memory = ({"text": text, "importance": data.get("importance") or 1}
              if isinstance(text, str) and text.strip() else None)
    return {"change": data.get("change") is True, "ops": ops, "memory": memory,
            "affinity": data.get("affinity") or 0}


# --- small helpers -------------------------------------------------------------

def _who(me: dict) -> str:
    return (f"You are {me['name']}, a {me['age']}-year-old {me['job'].lower()} "
            f"(you work at the {me['workplace']}). Personality: {me['personality']}")


def _state(me: dict) -> str:
    needs, inv = me["needs"], me["inventory"]
    carry = ", ".join(f"{n} {item}" for item, n in sorted(inv.items())) or "nothing"
    feel = [_hunger(needs["hunger"])]
    if "tool" in needs:
        feel.append(_tool(needs["tool"]))
    return f"How you are: {'; '.join(feel)}. You have {with_copper(me['wealth'])} and carry {carry}."


def _hunger(h: float) -> str:
    return ("not hungry" if h < 25 else "a little hungry" if h < 50
            else "hungry" if h < 75 else "starving")


def _tool(t: int) -> str:
    return ("your farming tools are in good shape" if t > 60 else
            "your farming tools are wearing down" if t > 25 else
            "your farming tools are nearly worn out" if t > 0 else
            "your farming tools are broken — you can't farm without new ones")


_FEELING = {"dislike": "you dislike them", "wary": "you're wary of them",
            "neutral": "nothing in particular", "like": "you like them",
            "close friend": "they're a close friend"}


def _affinity(a: int) -> str:
    """The -30..30 scale in words (thresholds in conversation.affinity_level)."""
    return _FEELING[conversation.affinity_level(a)]


def _reason(v: dict) -> str:
    topic = v["topic"]
    return {
        "trade": f"you want to buy {topic.get('item', 'something')} from them.",
        "appointment": f"you arranged to meet them here ({topic.get('why') or 'no reason given'}).",
        "news": "you have news to tell them.",
        "chat": "you felt like a chat.",
    }.get(v["reason"], "you wanted to talk.")


def _doing(block: dict) -> str:
    who = f" with {block['with']}" if block["with"] else ""
    return f"{block['do']} at {block['at']}{who} until {block['until']}"


def _goods(label: str, prices: dict, note: str) -> str:
    if not prices:
        return ""
    return f"{label}: " + ", ".join(f"{item} {p}c" for item, p in prices.items()) + f" ({note})."


def _deal(d: dict) -> str:
    return (f"{d['buyer']} bought {d['quantity']} {d['item']} from {d['seller']} "
            f"for {with_copper(d['price'], d['quantity'])}")


def _offer(o: dict, partner: str) -> str:
    amount = with_copper(o["price"], o["quantity"])
    if o["kind"] == "buy":
        return f"{partner} wants to buy {o['quantity']} {o['item']} from you for {amount}"
    return f"{partner} wants to sell you {o['quantity']} {o['item']} for {amount}"
