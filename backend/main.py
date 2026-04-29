# backend/main.py
from fastapi import FastAPI
from backend.database import init_db, get_db
from backend.agents.loader import load_agents_from_json

app = FastAPI()


@app.on_event("startup")
def startup():
    init_db()
    load_agents_from_json()


@app.get("/")
def root():
    return {"status": "Medieval AI Village running"}


@app.get("/villagers")
def get_villagers():
    db = next(get_db())
    from backend.database import AgentState
    agents = db.query(AgentState).all()
    return [{"id": a.id, "name": a.name, "job": a.job, "wealth": a.wealth, "location": a.location} for a in agents]