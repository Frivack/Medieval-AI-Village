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
#      Waking up comes first: the villager plans the day once.
# The only LLM calls: conversation lines, the replan after a conversation
# and the plan at waking (backend/llm/providers.py picks Claude or the
# templates; a failed call falls back to the template).
from backend.config import MINUTES_PER_TICK
from backend.database import SessionLocal, AgentState, TickHistory, SimState
from backend.llm import providers, usage
from backend.memory.short_term import remember
from backend.sim import conversation, economy, schedule, speech
from backend.sim.actions import ActionType
from backend.sim.clock import game_time  # re-exported for main.py
from backend.world.map import village_map
from backend.world.pathfinding import find_path

# (view -> turn, view -> plan), chosen once by config.CONVERSATION_LLM.
SPEAK, PLAN = providers.conversation_functions()


def run_tick(use_llm: bool = True) -> dict:
    """One tick. use_llm=False runs it on the templates even when Claude is
    configured — the runner does that after repeated failed ticks, so a
    tick that keeps failing doesn't keep paying for the same calls."""
    speak, plan = (SPEAK, PLAN) if use_llm else (speech.template_turn, speech.template_replan)
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
                conversation.end(convo, by_id, "bedtime", tick, relations, plan)
                continue
            out = conversation.advance(convo, by_id, tick, relations, speak, plan)
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
                entry = _step_agent(db, agent, agents, by_id, time, relations, busy,
                                    speak_fn=speak, plan_fn=plan)
            db.add(TickHistory(tick=tick, agent_id=agent.id, action=entry["action"],
                               dialogue=entry.get("dialogue"), gold_change=0))
            # A deal settles both sides at once: one TRADE row per side.
            for t in entry.get("trades", []):
                db.add(TickHistory(tick=tick, agent_id=t["agent_id"], action=t["action"],
                                   gold_change=t["copper_change"]))
            results.append({"agent": agent.name, "location": agent.location,
                            "status": agent.status,
                            "hunger": (agent.needs or {}).get("hunger"), **entry})

        # Today's LLM usage rides along with the tick, so the daily call
        # limit survives a restart (main.py restores it at startup).
        sim.llm_usage = usage.snapshot()
        db.commit()
        return {**time, "results": results}
    finally:
        db.close()


def _talk_entry(out: dict, by_id: dict) -> dict:
    return {"action": ActionType.TALK.value, "dialogue": out["line"],
            "detail": f"talking with {by_id[out['partner_id']].name}",
            "trades": out["trades"]}


def _step_agent(db, agent, agents, by_id, time: dict, relations, busy: set,
                speak_fn=None, plan_fn=None) -> dict:
    # The speaker/planner for this tick (run_tick passes them; defaults to
    # the configured pair, read at call time so tests can swap them).
    speak_fn, plan_fn = speak_fn or SPEAK, plan_fn or PLAN
    tick = time["tick"]
    needs = economy.needs_of(agent.job, agent.needs)
    plan = schedule.ensure(agent.daily_plan, agent.job, agent.workplace, tick)
    if plan != agent.daily_plan:
        agent.daily_plan = plan
    block = schedule.current(plan, tick)

    # Already walking somewhere → take the next step.
    if agent.path:
        return _advance_along_path(agent, tick)

    # Just woke up (asleep last tick, the sleep block is over) → plan the
    # day, once per day: keep the routine or change it.
    if (agent.status == "resting" and (block is None or block["do"] != schedule.SLEEP)
            and not schedule.is_planned(plan, time["day"])):
        return _plan_day(agent, by_id, tick, time["day"], plan_fn)

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
        out = conversation.advance(convo, by_id, tick, relations, speak_fn, plan_fn)
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

    # The schedule: what does this minute's block say? (A conversation or
    # a move above may have changed the plan, so look again.)
    block = schedule.current(agent.daily_plan, tick)
    if block is None:  # a cancelled block leaves free time: stay put
        agent.status = "idle"
        return {"action": ActionType.OBSERVE.value,
                "detail": f"free time at {agent.location}"}
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


def _plan_day(agent, by_id: dict, tick: int, day: int, plan_fn=None) -> dict:
    """The wake-up planner: one call that sees today's schedule and may
    edit it (validated like any other plan). Templates keep the routine.
    Like a tool call it only edits the schedule — whatever else a planner
    returns (a memory, affinity) is dropped here."""
    agent.daily_plan = schedule.mark_planned(agent.daily_plan, day)
    answer = (plan_fn or PLAN)(speech.wake_view(agent, tick))
    edits = {"change": answer.get("change"), "ops": answer.get("ops")}
    record = conversation.apply_plan(edits, agent, tick, [p.name for p in by_id.values()])
    agent.status = "planning"
    changes = "; ".join(record["applied"]) or "kept the routine"
    return {"action": ActionType.OBSERVE.value,
            "detail": f"woke up and planned the day: {changes}", "plan": record}


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
