import json
from pathlib import Path
from backend.database import SessionLocal, AgentState


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
        db_agent = AgentState(
            id=agent["id"],
            name=agent["name"],
            age=agent["age"],
            job=agent["job"],
            personality=agent["personality"],
            wealth=agent["initial_wealth"],
            location=agent["initial_location"],
            inventory=agent["initial_inventory"]
        )
        db.add(db_agent)

    db.commit()
    print(f"Loaded {len(data['agents'])} agents into DB.")
    db.close()