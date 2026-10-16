# backend/sim/speech.py
# What a villager says in a conversation, and what they make of it after.
#
# The engine (conversation.py) builds a *view* — everything one villager
# knows at that moment — and hands it to a *speaker* (view -> turn) or,
# once the conversation is over, a *replanner* (view -> plan). This module
# ships the template versions; stage 3 adds Claude versions with the same
# signatures, so the engine never changes (strategy pattern).
#
# turn = {"line": str, "end": bool,
#         "offer": None | {"kind": "buy"|"sell", "item", "quantity", "price"},
#         "response": None | "accept" | "reject",   # to the partner's pending offer
#         "share": None | memory}                    # news told in this line
# plan = {"change": bool, "ops": [...],              # schedule edits (stage 3)
#         "memory": None | {"text", "importance"}, "affinity": int}
import zlib

from backend.memory.short_term import news_for
from backend.sim import economy, schedule, trade
from backend.sim.clock import game_time
from backend.utils.currency import to_string


def speaker_view(convo, speaker, partner, now: int, affinity: int, lines_left: int) -> dict:
    needs = economy.needs_of(speaker.job, speaker.needs)
    pending = convo.pending_offer
    block = schedule.current(speaker.daily_plan, now)
    return {
        "conversation_id": convo.id,
        "me": {"name": speaker.name, "age": speaker.age, "job": speaker.job,
               "personality": speaker.personality, "wealth": speaker.wealth,
               "inventory": dict(speaker.inventory or {}), "needs": needs,
               "doing": schedule.describe(block) if block else None},
        "partner": {"name": partner.name, "job": partner.job},
        "affinity": affinity,
        "place": convo.place,
        "time": game_time(now),
        "i_started": convo.a_id == speaker.id,
        "reason": convo.reason,
        "topic": convo.topic or {},
        "transcript": [{"speaker": l["speaker"], "text": l["text"], "shared": l.get("shared", False)}
                       for l in convo.lines or []],
        # Only an offer the partner made is mine to answer.
        "pending_offer": pending if pending and pending["by"] == partner.id else None,
        "could_buy": trade.best_offer(speaker, partner, needs, convo.place),
        "partner_sells": {item: economy.unit_price(item, speaker.job, partner.job)
                          for item in economy.for_sale(partner.job, partner.workplace,
                                                       convo.place, partner.inventory or {})},
        "news": news_for(speaker, partner.name)[:3],
        "prices": dict(economy.BASE_PRICES),
        "lines_left": lines_left,
    }


def replan_view(convo, me, partner, now: int, affinity: int) -> dict:
    return {
        "me": {"name": me.name, "job": me.job, "personality": me.personality},
        "partner": {"name": partner.name, "job": partner.job},
        "affinity": affinity,
        "place": convo.place,
        "time": game_time(now),
        "reason": convo.reason,
        "transcript": [{"speaker": l["speaker"], "text": l["text"]} for l in convo.lines or []],
        "deals": list(convo.deals or []),
        "schedule": [schedule.describe(b) for b in schedule.blocks(me.daily_plan)],
    }


# --- the template speaker --------------------------------------------------

SMALL_TALK = {
    "Farmer": ["The wheat's coming up nicely this year.", "My back aches from the fields today."],
    "Blacksmith": ["The forge ran hot all day.", "Good iron is hard to come by these days."],
    "Merchant": ["Business is brisk, if you know where to look.", "Prices are moving, mark my words."],
    "Innkeeper": ["The kitchen never rests, but I wouldn't have it otherwise.",
                  "Always good to see a friendly face in here."],
}
REPLIES = ["Can't complain.", "Aye, same here.", "Busy as ever.", "Glad to hear it."]


def template_turn(v: dict) -> dict:
    """A plain but working conversational turn — no LLM. Answer the
    partner's offer, make my own if I want something they sell, share one
    piece of news in a social conversation, otherwise chat a little and
    say goodbye."""
    turn = {"line": "", "end": False, "offer": None, "response": None, "share": None}
    said = []
    me, partner = v["me"]["name"], v["partner"]["name"]
    transcript = v["transcript"]
    if len(transcript) < 2:                       # each side greets once
        said.append(f"{_greeting(v['time']['hour'])}, {partner}.")
    if transcript and transcript[-1]["shared"]:
        said.append("Is that so? Thanks for telling me.")

    if v["pending_offer"]:
        o = v["pending_offer"]
        turn["response"] = "accept"
        said.append(f"{o['quantity']} {_name(o['item'])} for {to_string(o['price'])}? Done.")
    if v["could_buy"] and v["lines_left"] > 1:
        o = v["could_buy"]
        turn["offer"] = o
        said.append(f"I'd like {o['quantity']} {_name(o['item'])}, if you can spare it "
                    f"- {to_string(o['price'])}?")

    if not turn["response"] and not turn["offer"]:
        already_shared = any(l["shared"] and l["speaker"] == me for l in transcript)
        if v["reason"] != "trade" and v["news"] and not already_shared and v["lines_left"] > 1:
            turn["share"] = v["news"][0]
            said.append(f"You know what? {v['news'][0]['text']}")
        elif v["reason"] == "chat" and len(transcript) < 2:
            if transcript:
                said.append(_pick(REPLIES, v))
            said.append(_pick(SMALL_TALK.get(v["me"]["job"], REPLIES), v))
        else:
            said.append(_goodbye(v))
            turn["end"] = True
    turn["line"] = " ".join(said)
    return turn


def template_replan(v: dict) -> dict:
    """No LLM, no judgment: the schedule and the relationship stay as they
    are; a social conversation leaves a one-line memory. (Deals and news
    are already remembered as they happen.)"""
    memory = None
    if not v["deals"]:
        memory = {"text": f"I talked with {v['partner']['name']} at {v['place']}.", "importance": 1}
    return {"change": False, "ops": [], "memory": memory, "affinity": 0}


def _greeting(hour: int) -> str:
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"


def _goodbye(v: dict) -> str:
    if v["me"]["job"] == "Innkeeper" and v["place"] == "Inn":
        return "Enjoy your evening."
    return "Well, I'd best be going. Take care."


def _name(item: str) -> str:
    return item.replace("_", " ")


def _pick(options: list[str], v: dict) -> str:
    """Deterministic variety: same conversation + same line -> same choice."""
    key = f"{v['conversation_id']}:{len(v['transcript'])}:{v['me']['name']}"
    return options[zlib.crc32(key.encode()) % len(options)]
