import json
from pathlib import Path
from backend.database import SessionLocal, AgentState
from backend.world.map import village_map


def load_agents_from_json():
    db = SessionLocal()

    if db.query(AgentState).count() > 0:
        print("Agents already loaded")
        db.close()
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

    db.commit()
    print(f"Loaded {len(data['agents'])} agents into DB.")
    db.close()