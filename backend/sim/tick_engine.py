# backend/sim/tick_engine.py
# Advances the world by one tick (= 1 in-game minute). Per agent, in order:
#   1. hunger grows (slower while asleep)
#   2. walking somewhere -> take the next step (1 tile per tick)
#   3. hungry and carrying food -> eat it
#   4. someone here sells what I want -> buy it
#   5. an urgent need (hungry with no food, broken tool) -> go where it's sold
#   6. otherwise the schedule (backend/sim/schedule.py): walk to the
#      block's place, then do what it says
# No LLM call here: rules and prices come from backend/sim/economy.py.
from backend.config import MINUTES_PER_TICK, SHORT_TERM_MEMORY_LIMIT
from backend.database import SessionLocal, AgentState, TickHistory, SimState
from backend.memory.store import memory_store
from backend.sim import economy, schedule
from backend.sim.actions import ActionType
from backend.sim.clock import game_time  # re-exported for main.py
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
            results.append({"agent": agent.name, "location": agent.location,
                            "status": agent.status,
                            "hunger": (agent.needs or {}).get("hunger"), **entry})

        db.commit()
        return {**time, "results": results}
    finally:
        db.close()


def _step_agent(db, agent, all_agents, time: dict) -> dict:
    tick = time["tick"]
    # 1) Hunger grows every tick, walking or not. Reassigning (rather than
    #    mutating) the JSON column is what makes SQLAlchemy save it.
    needs = economy.grow_hunger(economy.needs_of(agent.job, agent.needs),
                                asleep=agent.status == "resting",
                                minutes=MINUTES_PER_TICK)
    agent.needs = needs

    # 2) Already walking somewhere → take the next step.
    if agent.path:
        return _advance_along_path(agent, tick)

    # 3) Hungry and carrying food → eat it, wherever we are.
    if economy.should_eat(needs, agent.inventory or {}):
        agent.needs, agent.inventory = economy.eat(needs, agent.inventory or {})
        agent.status = "eating"
        return {"action": ActionType.EAT.value, "detail": f"ate a meal at {agent.location}"}

    # 4) Someone here sells what I want → buy it.
    bought = _shop(agent, all_agents, needs, tick)
    if bought:
        return bought

    # 5) An urgent need outranks the schedule: go where it's sold.
    errand = _errand(agent, all_agents, needs)
    if errand and errand[0] != agent.location:
        place, item = errand
        result = _start_move(agent, place, tick)
        result["detail"] = f"set off to {place} to buy {item}"
        return result

    # 6) The schedule: what does this minute's block say?
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

    agent.talking_to = None
    if block["do"] == schedule.WORK:
        return _do_work(agent, time)
    if block["do"] == schedule.SLEEP:
        agent.status = "resting"
        return {"action": ActionType.REST.value, "detail": f"sleeping at {agent.location}"}
    if block["do"] == schedule.SOCIAL:
        agent.status = "socializing"
        return {"action": ActionType.OBSERVE.value,
                "detail": f"spending the evening at {agent.location}"}
    # VISIT: wait there (stage 2 starts the appointment's conversation).
    agent.status = "visiting"
    who = f" for {block['with']}" if block["with"] else ""
    why = f" to {block['why']}" if block["why"] else ""
    return {"action": ActionType.OBSERVE.value,
            "detail": f"visiting {agent.location}{who}{why}"}


def _sellers_here(agent, all_agents):
    """Agents who could trade with `agent` right now: same building,
    standing still, awake."""
    if agent.location not in village_map.buildings:
        return []
    return [s for s in all_agents
            if s.id != agent.id and s.location == agent.location
            and not s.path and s.status != "resting"]


def _shop(agent, all_agents, needs: dict, tick: int):
    """Buy the most important thing on the agent's wish list that someone
    here sells, as many as wanted / on offer / affordable. None if nothing."""
    sellers = _sellers_here(agent, all_agents)
    if not sellers:
        return None
    for item, wanted in economy.wants(agent.job, agent.inventory or {}, needs).items():
        offers = []
        for s in sellers:
            on_offer = economy.for_sale(s.job, s.workplace, s.location, s.inventory or {}).get(item, 0)
            if on_offer:
                offers.append((economy.unit_price(item, agent.job, s.job), on_offer, s))
        if not offers:
            continue
        price, on_offer, seller = min(offers, key=lambda o: o[0])   # cheapest seller here
        quantity = min(wanted, on_offer, agent.wealth // price)
        if quantity >= 1:
            return _settle(agent, seller, item, quantity, price * quantity, tick)
    return None


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


def _settle(buyer, seller, item: str, quantity: int, total: int, tick: int) -> dict:
    """Move goods and copper both ways. Callers have checked stock and funds."""
    buyer.inventory = economy.add_item(buyer.inventory or {}, item, quantity)
    seller.inventory = economy.add_item(seller.inventory or {}, item, -quantity)
    buyer.wealth -= total
    seller.wealth += total
    buyer.status = "trading"
    buyer.talking_to = None
    # Buying the daily meals is routine; a deal over wheat or tools is news.
    importance = 1 if item == "food" else 3
    _remember(buyer, tick, f"I bought {quantity} {item} from {seller.name} for {to_string(total)}.",
              importance)
    _remember(seller, tick, f"I sold {quantity} {item} to {buyer.name} for {to_string(total)}.",
              importance)
    return {
        "action": ActionType.TRADE.value,
        "detail": f"bought {quantity} {item} from {seller.name} for {to_string(total)}",
        "copper_change": -total,
        "seller_side": {"agent_id": seller.id, "copper_change": total},
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
        _remember(agent, time["tick"], f"I produced {item} at {agent.location}.")
    if event.endswith("the tool broke"):
        _remember(agent, time["tick"],
                  "My farming tools broke; I can't work the fields without new ones.", 2)
    return {"action": ActionType.WORK.value, "detail": f"{event} at {agent.location}"}
