# backend/main.py
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.config import TICKS_PER_DAY
from backend.database import init_db, get_db, AgentState, TickHistory, SimState
from backend.agents.loader import load_agents_from_json
from backend.sim.tick_engine import run_tick, game_time
from backend.world.map import village_map


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Replaces the deprecated @app.on_event("startup").
    init_db()
    load_agents_from_json()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "Medieval AI Village running"}


@app.get("/villagers")
def get_villagers(db: Session = Depends(get_db)):
    # Depends() runs the get_db generator to completion after the
    # response, so the session is actually closed. Calling next(get_db())
    # by hand leaks the session — under frontend polling that exhausts
    # the connection pool (QueuePool limit reached -> HTTP 500).
    agents = db.query(AgentState).all()
    return [
        {
            "id": a.id, "name": a.name, "job": a.job,
            "wealth": a.wealth, "location": a.location,
            "x": a.x, "y": a.y, "status": a.status,
            "inventory": a.inventory,
        }
        for a in agents
    ]


@app.post("/tick")
def advance_tick(count: int = 1):
    """Advance the simulation by `count` ticks (1 tick = 5 in-game minutes)."""
    count = max(1, min(count, TICKS_PER_DAY))  # cap: one full day per request
    return [run_tick() for _ in range(count)]


@app.get("/time")
def get_time(db: Session = Depends(get_db)):
    sim = db.get(SimState, 1)
    return game_time(sim.tick if sim else 0)


@app.get("/map")
def get_map():
    return village_map.to_dict()


@app.get("/history")
def get_history(limit: int = 50, db: Session = Depends(get_db)):
    """Recent events, newest first. copper_change is +/- copper for TRADE rows."""
    rows = (db.query(TickHistory)
              .order_by(TickHistory.id.desc())
              .limit(limit).all())
    return [
        {"tick": r.tick, "agent_id": r.agent_id,
         "action": r.action, "dialogue": r.dialogue,
         "copper_change": r.gold_change}
        for r in rows
    ]


# Serve the built frontend (frontend/dist) at "/". Mounted last so the
# API routes above always win; html=True makes "/" serve index.html.
# The dist build is committed to the repo so the deployment box needs
# no Node.js — `git pull` + restart is the whole frontend deploy.
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
