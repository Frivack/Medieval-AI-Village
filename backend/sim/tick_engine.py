# backend/sim/tick_engine.py
# Advances the world by one tick (= one in-game hour).
# Per agent: continue an in-progress move (1 tile per tick), otherwise
# ask the decider for a new action and execute it.
from backend.config import TICKS_PER_DAY, TICKS_PER_HOUR, MINUTES_PER_TICK
from backend.database import SessionLocal, AgentState, TickHistory, SimState
from backend.sim.actions import ActionType, JOB_PRODUCT
from backend.sim.decider import decide
from backend.world.map import village_map
from backend.world.pathfinding import find_path


def game_time(tick: int) -> dict:
    day_tick = tick % TICKS_PER_DAY
    return {
        "tick": tick,
        "day": tick // TICKS_PER_DAY + 1,
        "hour": day_tick // TICKS_PER_HOUR,
        "minute": (day_tick % TICKS_PER_HOUR) * MINUTES_PER_TICK,
    }


def run_tick() -> dict:
    db = SessionLocal()
    try:
        sim = db.get(SimState, 1)
        if sim is None:
            sim = SimState(id=1, tick=0)
            db.add(sim)

        sim.tick += 1
        time = game_time(sim.tick)
        agents = db.query(AgentState).all()
        results = []

        for agent in agents:
            entry = _step_agent(db, agent, agents, time)
            db.add(TickHistory(
                tick=sim.tick,
                agent_id=agent.id,
                action=entry["action"],
                dialogue=entry.get("dialogue"),
            ))
            results.append({"agent": agent.name, **entry})

        db.commit()
        return {**time, "results": results}
    finally:
        db.close()


def _step_agent(db, agent, all_agents, time: dict) -> dict:
    # 1) Already walking somewhere → take the next step (1 tile per tick).
    if agent.path:
        return _advance_along_path(agent)

    # 2) Asleep at night → stay asleep, no re-decision (and no LLM call)
    #    every 5 minutes. Agents wake up at 06:00.
    if agent.status == "resting" and (time["hour"] >= 22 or time["hour"] < 6):
        return {"action": ActionType.REST.value,
                "detail": f"sleeping at {agent.location}"}

    # 3) Idle → decide a new action.
    ctx = _world_context(agent, all_agents, time)
    decision = decide(agent, ctx)
    action = decision["action"]

    if action == ActionType.MOVE:
        return _start_move(agent, decision.get("target"))
    if action == ActionType.WORK:
        return _do_work(agent, time)
    if action == ActionType.TALK:
        return _do_talk(agent, all_agents, decision)
    if action == ActionType.REST:
        agent.status = "resting"
        agent.talking_to = None
        return {"action": ActionType.REST.value, "detail": f"resting at {agent.location}"}
    # TRADE is not implemented yet — treated as OBSERVE for now.
    agent.status = "observing"
    agent.talking_to = None
    return {"action": ActionType.OBSERVE.value, "detail": f"looking around {agent.location}"}


def _world_context(agent, all_agents, time: dict) -> dict:
    nearby = [a.name for a in all_agents
              if a.id != agent.id and a.location == agent.location]
    return {
        **time,
        "nearby_agents": nearby,
        "buildings": list(village_map.buildings.keys()),
    }


def _advance_along_path(agent) -> dict:
    path = list(agent.path)
    agent.x, agent.y = path.pop(0)
    agent.path = path  # reassign so SQLAlchemy notices the JSON change
    agent.status = "moving"

    if not path:  # arrived
        building = village_map.building_at(agent.x, agent.y)
        agent.location = building.name if building else "Outdoors"
        agent.status = "idle"
        return {"action": ActionType.MOVE.value,
                "detail": f"arrived at {agent.location}"}
    return {"action": ActionType.MOVE.value,
            "detail": f"walking, {len(path)} tiles to go"}


def _start_move(agent, target) -> dict:
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
    return _advance_along_path(agent)  # first step happens this tick


def _do_work(agent, time: dict) -> dict:
    agent.status = "working"
    agent.talking_to = None
    product = JOB_PRODUCT.get(agent.job)
    # Output rate is 1 item per in-game hour, not per tick: only the
    # on-the-hour tick (minute == 0) yields the finished product.
    if product and time["minute"] == 0:
        inventory = dict(agent.inventory or {})
        inventory[product] = inventory.get(product, 0) + 1
        agent.inventory = inventory
        return {"action": ActionType.WORK.value,
                "detail": f"produced 1 {product} at {agent.location}"}
    return {"action": ActionType.WORK.value,
            "detail": f"working at {agent.location}"}


def _do_talk(agent, all_agents, decision: dict) -> dict:
    target_name = decision.get("target")
    partner = next((a for a in all_agents
                    if a.name == target_name and a.location == agent.location), None)
    if partner is None:
        agent.status = "observing"
        return {"action": ActionType.OBSERVE.value,
                "detail": f"wanted to talk to {target_name}, but they're not here"}
    agent.status = "talking"
    agent.talking_to = partner.id
    dialogue = decision.get("dialogue") or "..."
    return {"action": ActionType.TALK.value, "dialogue": dialogue,
            "detail": f"talking to {partner.name}"}
