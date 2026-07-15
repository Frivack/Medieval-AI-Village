# backend/sim/tick_engine.py
# Advances the world by one tick (= 5 in-game minutes).
# Per agent: continue an in-progress move (1 tile per tick), otherwise
# ask the decider for a new action and execute it.
from backend.config import SHORT_TERM_MEMORY_LIMIT
from backend.database import SessionLocal, AgentState, TickHistory, SimState
from backend.memory.store import memory_store
from backend.sim.actions import ActionType, JOB_PRODUCT
from backend.sim.clock import game_time  # re-exported for main.py
from backend.sim.decider import decide
from backend.sim.prices import price_of
from backend.utils.currency import to_string
from backend.world.map import village_map
from backend.world.pathfinding import find_path


def _remember(agent, tick: int, text: str, importance: int = 1) -> None:
    """Append one observation to the agent's short-term memory (ring
    buffer on the DB row) and to the optional long-term vector store.

    importance (1-3) feeds prompt selection: without it, one evening of
    small talk pushes a day-old trade out of the prompt window (recency
    alone drowns rare-but-important events in frequent chatter).
    """
    memories = list(agent.short_term_memory or [])
    memories.append({"tick": tick, "text": text, "importance": importance})
    # Reassign so SQLAlchemy notices the JSON change (same as agent.path).
    agent.short_term_memory = memories[-SHORT_TERM_MEMORY_LIMIT:]
    memory_store.add(agent.id, tick, text)


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
            # A trade settles for two agents at once; the seller side is
            # recorded as its own history row so both incomes are queryable.
            seller_side = entry.pop("seller_side", None)
            db.add(TickHistory(
                tick=sim.tick,
                agent_id=agent.id,
                action=entry["action"],
                dialogue=entry.get("dialogue"),
                gold_change=entry.get("copper_change", 0),
            ))
            if seller_side:
                db.add(TickHistory(
                    tick=sim.tick,
                    agent_id=seller_side["agent_id"],
                    action=ActionType.TRADE.value,
                    gold_change=seller_side["copper_change"],
                ))
            results.append({"agent": agent.name, **entry})

        db.commit()
        return {**time, "results": results}
    finally:
        db.close()


def _step_agent(db, agent, all_agents, time: dict) -> dict:
    # 1) Already walking somewhere → take the next step (1 tile per tick).
    if agent.path:
        return _advance_along_path(agent, time["tick"])

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
        return _start_move(agent, decision.get("target"), time["tick"])
    if action == ActionType.WORK:
        return _do_work(agent, time)
    if action == ActionType.TALK:
        return _do_talk(agent, all_agents, decision, time["tick"])
    if action == ActionType.TRADE:
        return _do_trade(agent, all_agents, decision, time["tick"])
    if action == ActionType.REST:
        agent.status = "resting"
        agent.talking_to = None
        return {"action": ActionType.REST.value, "detail": f"resting at {agent.location}"}
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


def _advance_along_path(agent, tick: int) -> dict:
    path = list(agent.path)
    agent.x, agent.y = path.pop(0)
    agent.path = path  # reassign so SQLAlchemy notices the JSON change
    agent.status = "moving"

    if not path:  # arrived
        building = village_map.building_at(agent.x, agent.y)
        agent.location = building.name if building else "Outdoors"
        agent.status = "idle"
        _remember(agent, tick, f"I arrived at {agent.location}.")
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
    agent.talking_to = None
    product = JOB_PRODUCT.get(agent.job)
    # Output rate is 1 item per in-game hour, not per tick: only the
    # on-the-hour tick (minute == 0) yields the finished product.
    if product and time["minute"] == 0:
        inventory = dict(agent.inventory or {})
        inventory[product] = inventory.get(product, 0) + 1
        agent.inventory = inventory
        _remember(agent, time["tick"], f"I produced 1 {product} at {agent.location}.")
        return {"action": ActionType.WORK.value,
                "detail": f"produced 1 {product} at {agent.location}"}
    return {"action": ActionType.WORK.value,
            "detail": f"working at {agent.location}"}


def _do_trade(agent, all_agents, decision: dict, tick: int) -> dict:
    """Buyer-initiated trade: `agent` buys item x quantity from `target`.

    Settles atomically at the base price — validates partner presence,
    seller stock and buyer funds, then moves items and copper both ways.
    Any failed precondition degrades to OBSERVE, like _do_talk/_start_move.
    """
    target_name = decision.get("target")
    item = decision.get("item")
    try:
        quantity = max(1, int(decision.get("quantity") or 1))
    except (TypeError, ValueError):
        quantity = 1

    seller = next((a for a in all_agents
                   if a.name == target_name and a.location == agent.location
                   and a.id != agent.id), None)
    fail = None
    if seller is None:
        fail = f"wanted to buy from {target_name}, but they're not here"
    elif (total := price_of(item, quantity)) is None:
        fail = f"wanted to buy unknown item '{item}'"
    elif (seller.inventory or {}).get(item, 0) < quantity:
        fail = f"{seller.name} has no {item} to sell"
    elif agent.wealth < total:
        fail = f"can't afford {quantity} {item} ({to_string(total)})"
    if fail:
        agent.status = "observing"
        agent.talking_to = None
        return {"action": ActionType.OBSERVE.value, "detail": fail}

    buyer_inv = dict(agent.inventory or {})
    buyer_inv[item] = buyer_inv.get(item, 0) + quantity
    agent.inventory = buyer_inv
    seller_inv = dict(seller.inventory)
    seller_inv[item] -= quantity
    if seller_inv[item] == 0:
        del seller_inv[item]
    seller.inventory = seller_inv
    agent.wealth -= total
    seller.wealth += total

    agent.status = "trading"
    agent.talking_to = None
    _remember(agent, tick,
              f"I bought {quantity} {item} from {seller.name} for {to_string(total)}.",
              importance=3)
    _remember(seller, tick,
              f"I sold {quantity} {item} to {agent.name} for {to_string(total)}.",
              importance=3)
    return {
        "action": ActionType.TRADE.value,
        "detail": f"bought {quantity} {item} from {seller.name} for {to_string(total)}",
        "copper_change": -total,
        "seller_side": {"agent_id": seller.id, "copper_change": total},
    }


def _do_talk(agent, all_agents, decision: dict, tick: int) -> dict:
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
    # Both sides remember the exchange — that's what makes later
    # conversations (and eventually retrieval) feel coherent.
    _remember(agent, tick, f'I said to {partner.name}: "{dialogue}"', importance=2)
    _remember(partner, tick, f'{agent.name} said to me: "{dialogue}"', importance=2)
    return {"action": ActionType.TALK.value, "dialogue": dialogue,
            "detail": f"talking to {partner.name}"}
