# backend/sim/conversation.py
# 1:1 conversations, one line per tick (stage 2 of the CLAUDE.md §6 redesign).
#
#   pick()    — code decides who starts talking to whom, and why
#   start()   — opens the conversation; the initiator speaks first
#   advance() — the next speaker says one line: answer the pending offer
#               (accept -> settle at once), make an offer, share news
#   end()     — goodbye / max lines / bedtime; then each side replans once
#               (schedule edits validated by schedule.apply_ops)
#
# What gets said and planned comes from speaker/planner functions: the
# templates in backend/sim/speech.py or Claude (backend/llm/claude.py),
# picked by backend/llm/providers.py — same view in, same turn out.
import random

from backend.config import TICKS_PER_HOUR
from backend.database import Conversation, Relationship
from backend.memory.short_term import mark_told, news_for, remember
from backend.sim import economy, schedule, speech, trade
from backend.world.map import village_map

MAX_LINES = 8
COOLDOWN_TICKS = 2 * TICKS_PER_HOUR   # same pair can't chat again for 2 in-game hours
CHAT_CHANCE = 0.05                    # per free pair, per minute of shared leisure
# Affinity is a long scale: in the 2-day model comparison a pair gained
# ~1.5 a day (at most 3), so "close friend" (20, prompts._affinity) takes
# one to two weeks of good meetings. A planner answers -2..+2 per
# conversation; a drop counts three times as much as a gain — trust is
# lost faster than it's won.
AFFINITY_RANGE = (-30, 30)
AFFINITY_STEP = 2                     # the most a planner can move it per conversation
NEGATIVE_WEIGHT = 3


class Relations:
    """The relationships table, loaded once per tick; rows made on demand."""

    def __init__(self, db):
        self.db = db
        self.rows = {(r.agent_id, r.other_id): r for r in db.query(Relationship)}

    def get(self, agent_id: str, other_id: str) -> Relationship:
        row = self.rows.get((agent_id, other_id))
        if row is None:
            row = Relationship(agent_id=agent_id, other_id=other_id, affinity=0)
            self.db.add(row)
            self.rows[(agent_id, other_id)] = row
        return row

    def affinity(self, agent_id: str, other_id: str) -> int:
        row = self.rows.get((agent_id, other_id))
        return row.affinity if row and row.affinity is not None else 0

    def recently_talked(self, a_id: str, b_id: str, now: int) -> bool:
        ticks = [r.last_talk_tick for r in (self.rows.get((a_id, b_id)), self.rows.get((b_id, a_id)))
                 if r is not None and r.last_talk_tick is not None]
        return bool(ticks) and now - max(ticks) < COOLDOWN_TICKS


def active(db) -> list[Conversation]:
    return db.query(Conversation).filter_by(status="active").order_by(Conversation.id).all()


def pick(agent, agents, now: int, relations: Relations, busy: set):
    """(partner, reason, topic) for a conversation `agent` should start now,
    or None. Business first, then appointments, then leisure."""
    if agent.location not in village_map.buildings:
        return None
    free = [p for p in agents
            if p.id != agent.id and p.id not in busy and p.location == agent.location
            and not p.path and p.status != "resting"]
    if not free:
        return None
    needs = economy.needs_of(agent.job, agent.needs)
    urgent = economy.urgent(agent.job, agent.inventory or {}, needs)

    # 1) Trade: someone here sells what I want. The cooldown doesn't apply
    #    to an urgent need — nobody should go hungry over etiquette.
    for p in free:
        offer = trade.best_offer(agent, p, needs, agent.location)
        if offer and (offer["item"] == urgent or not relations.recently_talked(agent.id, p.id, now)):
            return p, "trade", {"item": offer["item"]}

    # 2) Appointment: my schedule says I'm here to see this person.
    block = schedule.current(agent.daily_plan, now)
    if block and block["do"] == schedule.VISIT and block["with"]:
        for p in free:
            if p.name == block["with"]:
                return p, "appointment", {"why": block["why"]}

    # 3) Leisure: only off work, and only with someone free to listen.
    if not _at_leisure(block):
        return None
    for p in free:
        if relations.recently_talked(agent.id, p.id, now) or not _receptive(p, now):
            continue
        news = news_for(agent, p.name)
        if news:
            return p, "news", {"memory": news[0]}
        if random.Random(f"{now}:{agent.id}:{p.id}").random() < CHAT_CHANCE:
            return p, "chat", {}
    return None


def start(db, initiator, partner, reason: str, topic: dict, now: int) -> Conversation:
    convo = Conversation(a_id=initiator.id, b_id=partner.id, place=initiator.location,
                         reason=reason, topic=topic, started_tick=now, status="active",
                         next_speaker_id=initiator.id, lines=[], deals=[])
    db.add(convo)
    db.flush()   # assigns convo.id, which the template speaker uses for variety
    for me, other in ((initiator, partner), (partner, initiator)):
        me.talking_to = other.id
        me.status = "talking"
    return convo


def advance(convo, by_id: dict, now: int, relations: Relations,
            speaker_fn=speech.template_turn, replan_fn=speech.template_replan) -> dict:
    """The next speaker says one line. Returns {"speaker_id", "partner_id",
    "line", "trades": [history events], "ended": bool}."""
    speaker = by_id[convo.next_speaker_id]
    partner = by_id[convo.b_id if speaker.id == convo.a_id else convo.a_id]
    lines = list(convo.lines or [])
    view = speech.speaker_view(convo, speaker, partner, now,
                               relations.affinity(speaker.id, partner.id), MAX_LINES - len(lines))
    turn = _clean(speaker_fn(view))

    trades, note = [], None
    pending = convo.pending_offer
    if pending and pending["by"] == partner.id:
        if turn["response"] == "accept":
            trades, note = _close_deal(convo, pending, maker=partner, taker=speaker, now=now)
        convo.pending_offer = None      # accepted, refused or ignored: answered either way
    if turn["offer"]:
        convo.pending_offer = {**turn["offer"], "by": speaker.id}
    if turn["share"]:
        mark_told(speaker, turn["share"], partner.name)
        remember(partner, now, f"{speaker.name} told me: {turn['share']['text']}")

    lines.append({"tick": now, "speaker": speaker.name, "text": turn["line"],
                  "offer": turn["offer"], "response": turn["response"],
                  "shared": bool(turn["share"]), "note": note})
    convo.lines = lines
    convo.next_speaker_id = partner.id
    speaker.status = partner.status = "talking"

    ended = turn["end"] or len(lines) >= MAX_LINES
    if ended:
        end(convo, by_id, "goodbye" if turn["end"] else "max lines", now, relations, replan_fn)
    return {"speaker_id": speaker.id, "partner_id": partner.id, "line": turn["line"],
            "trades": trades, "ended": ended}


def bedtime(convo, by_id: dict, now: int) -> bool:
    """A participant's schedule says it's time to sleep: stop talking."""
    for agent_id in (convo.a_id, convo.b_id):
        block = schedule.current(by_id[agent_id].daily_plan, now)
        if block and block["do"] == schedule.SLEEP:
            return True
    return False


def end(convo, by_id: dict, why: str, now: int, relations: Relations,
        replan_fn=speech.template_replan) -> None:
    convo.status = "ended"
    convo.ended_tick = now
    convo.end_reason = why
    convo.pending_offer = None           # an unanswered offer lapses
    a, b = by_id[convo.a_id], by_id[convo.b_id]
    people = [p.name for p in by_id.values()]
    replans = []
    for me, other in ((a, b), (b, a)):
        me.talking_to = None
        plan = replan_fn(speech.replan_view(convo, me, other, now,
                                            relations.affinity(me.id, other.id)))
        replans.append(_apply_replan(plan, me, other, now, relations, people))
    convo.replans = replans


def _close_deal(convo, offer: dict, maker, taker, now: int):
    """The taker accepted the maker's offer: settle it, or say why not."""
    buyer, seller = (maker, taker) if offer["kind"] == "buy" else (taker, maker)
    item, quantity = offer["item"], offer["quantity"]
    price = trade.clamp_price(item, quantity, offer["price"], buyer, seller)
    why_not = trade.check(buyer, seller, item, quantity, price, convo.place)
    if why_not:
        return [], f"deal fell through: {why_not}"
    convo.deals = list(convo.deals or []) + [
        {"tick": now, "item": item, "quantity": quantity, "price": price,
         "buyer": buyer.name, "seller": seller.name}]
    return trade.settle(buyer, seller, item, quantity, price, now), None


def apply_plan(plan: dict, agent, now: int, people) -> dict:
    """Apply a planner's answer to `agent`: validated schedule edits and
    the memory. Shared by the after-conversation and wake-up planners.
    Returns what happened, for the record."""
    applied, rejected = [], []
    if plan.get("change") and plan.get("ops"):
        agent.daily_plan, applied, rejected = schedule.apply_ops(
            agent.daily_plan, plan["ops"], now, workplace=agent.workplace,
            places=village_map.buildings, people=[p for p in people if p != agent.name])
    memory = plan.get("memory")
    text = memory.get("text") if isinstance(memory, dict) else None
    if isinstance(text, str) and text.strip():
        try:
            importance = max(1, min(3, int(memory.get("importance") or 1)))
        except (TypeError, ValueError):
            importance = 1
        remember(agent, now, text.strip(), importance)
    return {"who": agent.name, "applied": applied, "rejected": rejected,
            "memory": text.strip() if isinstance(text, str) and text.strip() else None}


def _apply_replan(plan: dict, me, other, now: int, relations: Relations, people) -> dict:
    record = apply_plan(plan, me, now, people)
    row = relations.get(me.id, other.id)
    row.last_talk_tick = now
    try:
        step = max(-AFFINITY_STEP, min(AFFINITY_STEP, int(plan.get("affinity") or 0)))
    except (TypeError, ValueError):
        step = 0
    if step < 0:
        step *= NEGATIVE_WEIGHT
    row.affinity = max(AFFINITY_RANGE[0], min(AFFINITY_RANGE[1], (row.affinity or 0) + step))
    return {**record, "affinity": step}


def _at_leisure(block) -> bool:
    # No block at all = free time a planner cancelled into existence.
    return block is None or block["do"] in (schedule.SOCIAL, schedule.VISIT)


def _receptive(partner, now: int) -> bool:
    """Free to chat: off work too, or working at their own place and so
    hosting visitors (the innkeeper at the Inn, the farmer at the Farm)."""
    block = schedule.current(partner.daily_plan, now)
    if _at_leisure(block):
        return True
    return bool(block) and block["do"] == schedule.WORK and partner.location == partner.workplace


def _clean(turn) -> dict:
    """Turns may come from a model: keep only well-formed fields."""
    turn = turn if isinstance(turn, dict) else {}
    line = turn.get("line")
    offer = turn.get("offer")
    if not (isinstance(offer, dict) and offer.get("kind") in ("buy", "sell")
            and isinstance(offer.get("item"), str) and isinstance(offer.get("quantity"), int)
            and offer["quantity"] >= 1 and isinstance(offer.get("price"), int)):
        offer = None
    share = turn.get("share")
    return {
        "line": line.strip() if isinstance(line, str) and line.strip() else "...",
        "end": turn.get("end") is True,
        "offer": {k: offer[k] for k in ("kind", "item", "quantity", "price")} if offer else None,
        "response": turn.get("response") if turn.get("response") in ("accept", "reject") else None,
        "share": share if isinstance(share, dict) and "text" in share and "tick" in share else None,
    }
