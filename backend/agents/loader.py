import json
from datetime import datetime
from pathlib import Path

from backend.config import START_AT_LOCAL_TIME
from backend.database import SessionLocal, AgentState, SimState
from backend.sim.clock import tick_for_time_of_day
from backend.world.map import village_map


def load_agents_from_json(db=None):
    """Create the world on first start: the villagers from data/agents.json
    and the clock. Does nothing if villagers already exist. `db` is for
    tests; the app passes none and gets its own session."""
    own = db is None
    db = db or SessionLocal()
    try:
        if db.query(AgentState).count() > 0:
            print("Agents already loaded")
            return

        json_path = Path(__file__).parent.parent.parent / "data" / "agents.json"
        with open(json_path, "r") as f:
            data = json.load(f)

        for agent in data["agents"]:
            # Spawn inside the building named by initial_location.
            building = village_map.buildings[agent["initial_location"]]
            x, y = building.interior
            db_agent = AgentState(
                id=agent["id"],
                name=agent["name"],
                age=agent["age"],
                job=agent["job"],
                personality=agent["personality"],
                wealth=agent["initial_wealth"],
                location=agent["initial_location"],
                workplace=agent["workplace"],
                x=x,
                y=y,
                path=[],
                inventory=agent["initial_inventory"]
            )
            db.add(db_agent)

        # The clock starts with the world: at 00:00, or at the server's
        # current time of day so a real-time village sleeps at night.
        if db.get(SimState, 1) is None:
            start = tick_for_time_of_day(datetime.now()) if START_AT_LOCAL_TIME else 0
            db.add(SimState(id=1, tick=start))

        db.commit()
        print(f"Loaded {len(data['agents'])} agents into DB.")
    finally:
        if own:
            db.close()
