# The conversation engine against a real (temporary) SQLite database,
# with the template speaker: no LLM involved.
from backend.database import Conversation
from backend.memory.short_term import news_for
from backend.sim import conversation as conv
from backend.sim import schedule, trade
from backend.sim.clock import tick_at
from tests.helpers import EVENING, villager


def run_conversation(db, initiator, everyone, now=EVENING):
    """pick + start + advance until it ends; returns the Conversation."""
    relations = conv.Relations(db)
    by_id = {a.id: a for a in everyone}
    partner, reason, topic = conv.pick(initiator, everyone, now, relations, busy=set())
    convo = conv.start(db, initiator, partner, reason, topic, now)
    out = conv.advance(convo, by_id, now, relations)
    while not out["ended"]:
        now += 1
        out = conv.advance(convo, by_id, now, relations)
    return convo


def test_a_trade_conversation_settles_the_deal(db):
    gilbert = villager(db, "Gilbert", "Merchant", "Market", {"food": 0})
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"food": 10})
    convo = run_conversation(db, gilbert, [gilbert, margaret])
    assert convo.reason == "trade" and convo.status == "ended" and convo.end_reason == "goodbye"
    assert gilbert.inventory["food"] == 3 and margaret.inventory["food"] == 7
    assert gilbert.wealth == 1000 - 36 and margaret.wealth == 1000 + 36
    assert [l["speaker"] for l in convo.lines][:2] == ["Gilbert", "Margaret"]   # turns alternate


def test_both_sides_can_buy_in_one_conversation(db):
    gilbert = villager(db, "Gilbert", "Merchant", "Market", {"wheat": 10})
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"food": 10})
    convo = run_conversation(db, gilbert, [gilbert, margaret])
    bought = {(d["buyer"], d["item"]) for d in convo.deals}
    assert bought == {("Gilbert", "food"), ("Margaret", "wheat")}


def test_a_deal_that_cannot_be_filled_falls_through(db):
    gilbert = villager(db, "Gilbert", "Merchant", "Market")
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"food": 10})
    relations = conv.Relations(db)
    convo = conv.start(db, gilbert, margaret, "trade", {}, EVENING)
    convo.pending_offer = {"by": gilbert.id, "kind": "buy", "item": "food",
                           "quantity": 50, "price": 600}           # she has 10, keeps 3
    convo.next_speaker_id = margaret.id                            # her turn to answer
    conv.advance(convo, {a.id: a for a in (gilbert, margaret)}, EVENING, relations,
                 speaker_fn=lambda v: {"line": "Fine.", "response": "accept"})
    assert convo.deals == [] and "fell through" in convo.lines[-1]["note"]
    assert margaret.inventory["food"] == 10


def test_a_model_cannot_set_an_absurd_price(db):
    gilbert = villager(db, "Gilbert", "Merchant", "Market")
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"food": 10})
    relations = conv.Relations(db)
    convo = conv.start(db, gilbert, margaret, "trade", {}, EVENING)
    convo.pending_offer = {"by": gilbert.id, "kind": "buy", "item": "food", "quantity": 3, "price": 1}
    convo.next_speaker_id = margaret.id                            # her turn to answer
    conv.advance(convo, {a.id: a for a in (gilbert, margaret)}, EVENING, relations,
                 speaker_fn=lambda v: {"line": "Fine.", "response": "accept"})
    assert convo.deals[0]["price"] == round(36 * 0.7)              # clamped to 70% of 3 x 12c


def test_news_is_told_once_and_remembered_by_the_listener(db):
    thomas = villager(db, "Thomas", "Farmer", "Farm", {"food": 3})
    edmund = villager(db, "Edmund", "Blacksmith", "Smithy", {"food": 3})
    thomas.short_term_memory = [{"tick": 1, "text": "I sold 10 wheat to Gilbert for 12s.",
                                 "importance": 3}]
    convo = run_conversation(db, thomas, [thomas, edmund])
    assert convo.reason == "news"
    assert any(m["text"] == "Thomas told me: I sold 10 wheat to Gilbert for 12s."
               for m in edmund.short_term_memory)
    assert thomas.short_term_memory[0]["told"] == ["Edmund"]


def test_cooldown_blocks_more_chat_but_not_an_urgent_need(db):
    thomas = villager(db, "Thomas", "Farmer", "Farm", {"food": 3})
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"food": 10})
    thomas.short_term_memory = [{"tick": 1, "text": "My farming tools broke.", "importance": 2}]
    run_conversation(db, thomas, [thomas, margaret])               # news -> cooldown starts
    relations = conv.Relations(db)
    later = EVENING + 30
    thomas.short_term_memory = thomas.short_term_memory + [
        {"tick": later, "text": "I bought 1 farming_tools from Edmund for 1g 10s.", "importance": 3}]
    assert conv.pick(thomas, [thomas, margaret], later, relations, set()) is None
    thomas.inventory = {}
    thomas.needs = {"hunger": 60.0, "tool": 100}                  # hungry, no food: urgent
    assert conv.pick(thomas, [thomas, margaret], later, relations, set())[1] == "trade"


def test_bedtime_and_max_lines_end_a_conversation(db):
    thomas = villager(db, "Thomas", "Farmer", "Farm", {"food": 3})
    edmund = villager(db, "Edmund", "Blacksmith", "Smithy", {"food": 3})
    by_id = {a.id: a for a in (thomas, edmund)}
    relations = conv.Relations(db)
    convo = conv.start(db, thomas, edmund, "chat", {}, EVENING)
    chatter = lambda v: {"line": "And another thing..."}           # never says goodbye
    for i in range(conv.MAX_LINES):
        out = conv.advance(convo, by_id, EVENING + i, relations, speaker_fn=chatter)
    assert out["ended"] and convo.end_reason == "max lines" and len(convo.lines) == conv.MAX_LINES
    late = conv.start(db, thomas, edmund, "chat", {}, tick_at(2, 22, 30))
    assert conv.bedtime(late, by_id, tick_at(2, 22, 30))


def test_ending_records_the_talk_for_both_sides(db):
    thomas = villager(db, "Thomas", "Farmer", "Farm", {"food": 3})
    edmund = villager(db, "Edmund", "Blacksmith", "Smithy", {"food": 3})
    convo = conv.start(db, thomas, edmund, "chat", {}, EVENING)
    conv.end(convo, {a.id: a for a in (thomas, edmund)}, "goodbye", EVENING, conv.Relations(db))
    db.flush()
    relations = conv.Relations(db)
    assert relations.recently_talked(thomas.id, edmund.id, EVENING + 10)
    assert not relations.recently_talked(thomas.id, edmund.id, EVENING + conv.COOLDOWN_TICKS)
    assert thomas.talking_to is None and edmund.talking_to is None
    assert db.query(Conversation).one().status == "ended"


def test_a_replan_edits_the_schedule_and_is_recorded(db):
    thomas = villager(db, "Thomas", "Farmer", "Farm")
    edmund = villager(db, "Edmund", "Blacksmith", "Smithy")
    relations = conv.Relations(db)
    by_id = {a.id: a for a in (thomas, edmund)}
    convo = conv.start(db, thomas, edmund, "chat", {}, EVENING)

    def planner(view):
        if view["me"]["name"] == "Edmund":     # a grudge: clamped to -2, drops count x3
            return {"change": False, "ops": [{"op": "cancel", "block": "anything"}],
                    "memory": None, "affinity": -5}
        return {"change": True, "affinity": 1,
                "memory": {"text": "Edmund will mend my plough tomorrow.", "importance": 3},
                "ops": [{"op": "insert", "day": 3, "from": "07:00", "to": "07:30", "do": "VISIT",
                         "at": "Smithy", "with": "Edmund", "why": "get the plough mended"},
                        {"op": "insert", "day": 3, "from": "07:03", "to": "08:00",
                         "do": "VISIT", "at": "Smithy"}]}

    conv.end(convo, by_id, "goodbye", EVENING, relations, planner)

    visit = schedule.current(thomas.daily_plan, tick_at(3, 7, 10))
    assert (visit["do"], visit["at"], visit["with"]) == ("VISIT", "Smithy", "Edmund")
    assert schedule.current(thomas.daily_plan, tick_at(3, 7, 40))["do"] == "WORK"   # routine resumes
    mine, his = convo.replans
    assert mine["who"] == "Thomas" and len(mine["applied"]) == 1
    assert len(mine["rejected"]) == 1 and "5-minute grid" in mine["rejected"][0]
    assert thomas.short_term_memory[-1] == {"tick": EVENING, "importance": 3,
                                            "text": "Edmund will mend my plough tomorrow."}
    assert his["applied"] == his["rejected"] == [] and his["affinity"] == -6
    assert relations.affinity("edmund", "thomas") == -6 and relations.affinity("thomas", "edmund") == 1


def test_affinity_is_a_long_scale_that_drops_faster_than_it_climbs(db):
    thomas = villager(db, "Thomas", "Farmer", "Farm")
    edmund = villager(db, "Edmund", "Blacksmith", "Smithy")
    relations, by_id = conv.Relations(db), {a.id: a for a in (thomas, edmund)}
    now = EVENING
    for raw in [2] * 20 + [-2, -1]:            # twenty great talks, then a row and a slight
        convo = conv.start(db, thomas, edmund, "chat", {}, now)
        conv.end(convo, by_id, "goodbye", now, relations,
                 lambda view: {"change": False, "ops": [], "memory": None, "affinity": raw})
        now += 1
    # +40 is capped at +30, then -6 and -3.
    assert relations.affinity("thomas", "edmund") == 30 - 6 - 3


def test_everyday_purchases_are_routine_memories_but_wheat_is_news(db):
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"ale": 5, "food": 5})
    gilbert = villager(db, "Gilbert", "Merchant", "Market", {"wheat": 5})
    trade.settle(gilbert, margaret, "ale", 1, 6, EVENING)        # Gilbert buys an ale
    trade.settle(margaret, gilbert, "wheat", 2, 36, EVENING)     # and sells her wheat
    assert [m["importance"] for m in gilbert.short_term_memory] == [1, 3]
    assert [m["text"] for m in news_for(gilbert, "Edmund")] == [gilbert.short_term_memory[1]["text"]]


def test_trade_memories_carry_the_copper_total_and_unit_price(db):
    margaret = villager(db, "Margaret", "Innkeeper", "Inn")
    gilbert = villager(db, "Gilbert", "Merchant", "Market", {"wheat": 10})
    trade.settle(margaret, gilbert, "wheat", 8, 140, EVENING)
    assert gilbert.short_term_memory[-1]["text"] == \
        "I sold 8 wheat to Margaret for 14s (140c, 17.5c each)."
    poor = villager(db, "Thomas", "Farmer", "Farm", wealth=10)
    assert trade.check(poor, gilbert, "wheat", 1, 15, "Inn") == "Thomas can't afford 1s 5c (15c)"
