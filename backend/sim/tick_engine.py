# backend/sim/tick_engine.py
# Advances the world by one tick (= 1 in-game minute).
#   1. everyone's hunger grows (slower while asleep)
#   2. every active conversation gets its next line (backend/sim/conversation.py);
#      bedtime ends one
#   3. everyone not talking acts, in order:
#        walking -> next step; hungry with food -> eat; a reason to talk to
#        someone here (trade, appointment, news, chat) -> start a
#        conversation; an urgent need -> go where it's sold; otherwise the
#        schedule (backend/sim/schedule.py)
# No LLM call happens here yet: lines come from templates (stage 2).
from backend.config import MINUTES_PER_TICK
from backend.database import SessionLocal, AgentState, TickHistory, SimState
from backend.memory.short_term import remember
from backend.sim import conversation, economy, schedule
from backend.sim.actions import ActionType
from backend.sim.clock import game_time  # re-exported for main.py
from backend.world.map import village_map
from backend.world.pathfinding import find_path


def run_tick() -> dict:
    db = SessionLocal()
    try:
        sim = db.get(SimState, 1)
        if sim is None:
            sim = SimState(id=1, tick=0)
            db.add(sim)

        sim.tick += 1
        tick = sim.tick
        time = game_time(tick)
        agents = db.query(AgentState).all()
        by_id = {a.id: a for a in agents}
        relations = conversation.Relations(db)

        # 1) Hunger grows for everyone, talking or not. Reassigning (rather
        #    than mutating) the JSON column is what makes SQLAlchemy save it.
        for a in agents:
            a.needs = economy.grow_hunger(economy.needs_of(a.job, a.needs),
                                          asleep=a.status == "resting",
                                          minutes=MINUTES_PER_TICK)

        # 2) Conversations: one line each.
        said, listening, busy = {}, {}, set()
        for convo in conversation.active(db):
            if conversation.bedtime(convo, by_id, tick):
                conversation.end(convo, by_id, "bedtime", tick, relations)
                continue
            out = conversation.advance(convo, by_id, tick, relations)
            said[out["speaker_id"]] = out
            listening[out["partner_id"]] = out["speaker_id"]
            if not out["ended"]:
                busy |= {convo.a_id, convo.b_id}

        # 3) Everyone else acts.
        results = []
        for agent in agents:
            if agent.id in said:
                entry = _talk_entry(said[agent.id], by_id)
            elif agent.id in listening or agent.id in busy:
                # Someone else spoke (or just started talking to me) this tick.
                other = by_id.get(listening.get(agent.id) or agent.talking_to)
                entry = {"action": ActionType.OBSERVE.value,
                         "detail": f"listening to {other.name if other else 'someone'}"}
            else:
                entry = _step_agent(db, agent, agents, by_id, time, relations, busy)
            db.add(TickHistory(tick=tick, agent_id=agent.id, action=entry["action"],
                               dialogue=entry.get("dialogue"), gold_change=0))
            # A deal settles both sides at once: one TRADE row per side.
            for t in entry.get("trades", []):
                db.add(TickHistory(tick=tick, agent_id=t["agent_id"], action=t["action"],
                                   gold_change=t["copper_change"]))
            results.append({"agent": agent.name, "location": agent.location,
                            "status": agent.status,
                            "hunger": (agent.needs or {}).get("hunger"), **entry})

        db.commit()
        return {**time, "results": results}
    finally:
        db.close()


def _talk_entry(out: dict, by_id: dict) -> dict:
    return {"action": ActionType.TALK.value, "dialogue": out["line"],
            "detail": f"talking with {by_id[out['partner_id']].name}",
            "trades": out["trades"]}


def _step_agent(db, agent, agents, by_id, time: dict, relations, busy: set) -> dict:
    tick = time["tick"]
    needs = economy.needs_of(agent.job, agent.needs)

    # Already walking somewhere → take the next step.
    if agent.path:
        return _advance_along_path(agent, tick)

    # Hungry and carrying food → eat it, wherever we are.
    if economy.should_eat(needs, agent.inventory or {}):
        agent.needs, agent.inventory = economy.eat(needs, agent.inventory or {})
        agent.status = "eating"
        return {"action": ActionType.EAT.value, "detail": f"ate a meal at {agent.location}"}

    # A reason to talk to someone here → start, and say the first line.
    picked = conversation.pick(agent, agents, tick, relations, busy)
    if picked:
        partner, reason, topic = picked
        convo = conversation.start(db, agent, partner, reason, topic, tick)
        busy |= {agent.id, partner.id}
        out = conversation.advance(convo, by_id, tick, relations)
        if out["ended"]:
            busy -= {agent.id, partner.id}
        return _talk_entry(out, by_id)

    # An urgent need outranks the schedule: go where it's sold.
    errand = _errand(agent, agents, needs)
    if errand and errand[0] != agent.location:
        place, item = errand
        result = _start_move(agent, place, tick)
        result["detail"] = f"set off to {place} to buy {item}"
        return result

    # The schedule: what does this minute's block say?
    plan = schedule.ensure(agent.daily_plan, agent.job, agent.workplace, tick)
    if plan != agent.daily_plan:
        agent.daily_plan = plan
    block = schedule.current(plan, tick)
    if block is None:  # the routine covers every minute; only a broken plan gets here
        agent.status = "idle"
        return {"action": ActionType.OBSERVE.value,
                "detail": f"nothing planned at {agent.location}"}
    if agent.location != block["at"]:
        return _start_move(agent, block["at"], tick)

    if block["do"] == schedule.WORK:
        return _do_work(agent, time)
    if block["do"] == schedule.SLEEP:
        agent.status = "resting"
        return {"action": ActionType.REST.value, "detail": f"sleeping at {agent.location}"}
    if block["do"] == schedule.SOCIAL:
        agent.status = "socializing"
        return {"action": ActionType.OBSERVE.value,
                "detail": f"spending the evening at {agent.location}"}
    agent.status = "visiting"
    who = f" for {block['with']}" if block["with"] else ""
    why = f" to {block['why']}" if block["why"] else ""
    return {"action": ActionType.OBSERVE.value,
            "detail": f"visiting {agent.location}{who}{why}"}


def _errand(agent, all_agents, needs: dict):
    """(place, item) to go to for an urgent need, if anyone awake sells
    it somewhere right now and the agent can afford it; else None."""
    item = economy.urgent(agent.job, agent.inventory or {}, needs)
    if item is None:
        return None
    for s in all_agents:
        if s.id == agent.id or s.path or s.status == "resting":
            continue
        if s.location not in village_map.buildings:
            continue
        if not economy.for_sale(s.job, s.workplace, s.location, s.inventory or {}).get(item):
            continue
        if agent.wealth >= economy.unit_price(item, agent.job, s.job):
            return s.location, item
    return None


def _advance_along_path(agent, tick: int) -> dict:
    path = list(agent.path)
    agent.x, agent.y = path.pop(0)
    agent.path = path  # reassign so SQLAlchemy notices the JSON change
    agent.status = "moving"

    if not path:  # arrived
        building = village_map.building_at(agent.x, agent.y)
        agent.location = building.name if building else "Outdoors"
        agent.status = "idle"
        remember(agent, tick, f"I arrived at {agent.location}.")
        return {"action": ActionType.MOVE.value,
                "detail": f"arrived at {agent.location}"}
    return {"action": ActionType.MOVE.value,
            "detail": f"walking, {len(path)} tiles to go"}


def _start_move(agent, target, tick: int) -> dict:
    building = village_map.buildings.get(target)
    if building is None:
        return {"action": ActionType.OBSERVE.value,
                "detail": f"wanted to go to unknown place '{target}'"}
    path = find_path(village_map, (agent.x, agent.y), building.interior)
    if not path:
        return {"action": ActionType.OBSERVE.value,
                "detail": f"no path to {target}"}
    agent.path = path
    agent.location = "Outdoors"
    agent.talking_to = None
    return _advance_along_path(agent, tick)  # first step happens this tick


def _do_work(agent, time: dict) -> dict:
    agent.status = "working"
    # Output comes once per in-game hour of work, on the minute-0 tick.
    if time["minute"] != 0:
        return {"action": ActionType.WORK.value, "detail": f"working at {agent.location}"}
    inventory, needs, event = economy.produce(
        agent.job, agent.inventory or {}, economy.needs_of(agent.job, agent.needs))
    agent.inventory, agent.needs = inventory, needs
    if event is None:   # nothing to make (the merchant tends his stall)
        return {"action": ActionType.WORK.value, "detail": f"working at {agent.location}"}
    if event.startswith("produced"):
        item = event.split(";")[0].removeprefix("produced ")
        remember(agent, time["tick"], f"I produced {item} at {agent.location}.")
    if event.endswith("the tool broke"):
        remember(agent, time["tick"],
                 "My farming tools broke; I can't work the fields without new ones.", 2)
    return {"action": ActionType.WORK.value, "detail": f"{event} at {agent.location}"}
