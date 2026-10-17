# backend/main.py
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.config import (CLAUDE_MODEL, CONVERSATION_LLM, LLM_DAILY_CALL_LIMIT,
                            MANUAL_TICK_ENABLED, MINUTES_PER_TICK,
                            TICK_INTERVAL_SECONDS, TICKS_PER_DAY)
from backend.database import (init_db, get_db, AgentState, Conversation, Relationship,
                              SessionLocal, TickHistory, SimState)
from backend.agents.loader import load_agents_from_json
from backend.llm import usage
from backend.sim import conversation, economy, schedule
from backend.sim.runner import run_tick_locked, tick_loop
from backend.sim.clock import format_clock
from backend.sim.tick_engine import game_time
from backend.world.map import village_map

# uvicorn configures only its own loggers; without a root handler the
# INFO lines from our modules (tick loop, vector memory) never show up.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     [%(name)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per LLM call otherwise


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Replaces the deprecated @app.on_event("startup").
    init_db()
    load_agents_from_json()
    restore_llm_usage()
    stop = asyncio.Event()
    loop_task = (asyncio.create_task(tick_loop(TICK_INTERVAL_SECONDS, stop))
                 if TICK_INTERVAL_SECONDS > 0 else None)
    yield
    # Shutdown (e.g. systemctl restart): let an in-flight tick finish and
    # commit first. If systemd's stop timeout kills us before that, SQLite
    # rolls the unfinished tick back — the world just loses that one tick.
    stop.set()
    if loop_task:
        await loop_task


def restore_llm_usage(db: Session = None) -> None:
    """Today's LLM usage as saved with the last tick, so a restart doesn't
    reset the daily call limit (backend/llm/usage.py)."""
    own = db is None
    db = db or SessionLocal()
    try:
        sim = db.get(SimState, 1)
        usage.restore(sim.llm_usage if sim else None)
    finally:
        if own:
            db.close()


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
    sim = db.get(SimState, 1)
    now = sim.tick if sim else 0
    return [
        {
            "id": a.id, "name": a.name, "job": a.job,
            "wealth": a.wealth, "location": a.location,
            "x": a.x, "y": a.y, "status": a.status,
            "inventory": a.inventory,
            "needs": economy.needs_of(a.job, a.needs),
            "activity": _activity(a.daily_plan, now),
            "recent_memories": (a.short_term_memory or [])[-5:],
        }
        for a in agents
    ]


def _activity(plan, now: int):
    """The schedule block in force at `now` (None before the first tick)."""
    block = schedule.current(plan, now)
    return schedule.describe(block) if block else None


@app.get("/villagers/{agent_id}")
def get_villager(agent_id: str, db: Session = Depends(get_db)):
    """One villager in full, for the detail view: the schedule from now to
    the end of tomorrow (blocks the AI added carry its reason), how they
    feel about each other villager and how each feels back, and their
    memories, newest first."""
    agent = db.get(AgentState, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"No villager '{agent_id}'.")
    sim = db.get(SimState, 1)
    now = sim.tick if sim else 0
    others = db.query(AgentState).filter(AgentState.id != agent_id).order_by(AgentState.name).all()
    feel = {(r.agent_id, r.other_id): r for r in db.query(Relationship).filter(
        or_(Relationship.agent_id == agent_id, Relationship.other_id == agent_id))}

    def relation(other):
        mine, theirs = feel.get((agent_id, other.id)), feel.get((other.id, agent_id))
        score = (mine.affinity or 0) if mine else 0
        back = (theirs.affinity or 0) if theirs else 0
        last = mine.last_talk_tick if mine else None
        return {"id": other.id, "name": other.name, "job": other.job,
                "affinity": score, "level": conversation.affinity_level(score),
                "their_affinity": back, "their_level": conversation.affinity_level(back),
                "last_talk": format_clock(last) if last is not None else None}

    return {
        "id": agent.id, "name": agent.name, "age": agent.age, "job": agent.job,
        "personality": agent.personality, "workplace": agent.workplace,
        "location": agent.location, "status": agent.status, "wealth": agent.wealth,
        "inventory": agent.inventory or {}, "needs": economy.needs_of(agent.job, agent.needs),
        "now": now,
        "schedule": [
            {"start": b["start"], "end": b["end"],
             "from": format_clock(b["start"]), "to": format_clock(b["end"]),
             "do": b["do"], "at": b["at"], "with": b["with"], "why": b["why"],
             "ai": b["source"] == schedule.AI, "current": b["start"] <= now < b["end"]}
            for b in schedule.blocks(agent.daily_plan) if b["end"] > now
        ],
        "relationships": [relation(o) for o in others],
        "memories": [
            {"tick": m["tick"], "time": format_clock(m["tick"]), "text": m["text"],
             "importance": m.get("importance", 1), "told": m.get("told", [])}
            for m in reversed(agent.short_term_memory or [])
        ],
    }


@app.post("/tick")
def advance_tick(count: int = 1):
    """Advance the simulation by `count` ticks (1 tick = 1 in-game minute).

    Manual time control for local dev. The public server turns it off
    (MANUAL_TICK_ENABLED=0): every tick costs LLM calls, so visitors must
    not be able to trigger them.
    """
    if not MANUAL_TICK_ENABLED:
        raise HTTPException(status_code=403, detail="Manual ticking is disabled on this server.")
    count = max(1, min(count, TICKS_PER_DAY))  # cap: one full day per request
    return [run_tick_locked() for _ in range(count)]


@app.get("/status")
def get_status():
    """How time advances on this server, and who writes the conversations.
    The frontend hides the manual tick controls when manual_tick is false,
    and converts ticks to clock times with minutes_per_tick instead of
    hard-coding the time scale. `llm` shows today's (UTC) calls and the
    estimated cost since the process started."""
    claude = CONVERSATION_LLM == "claude"
    return {
        "auto_tick": TICK_INTERVAL_SECONDS > 0,
        "tick_interval_seconds": TICK_INTERVAL_SECONDS,
        "manual_tick": MANUAL_TICK_ENABLED,
        "minutes_per_tick": MINUTES_PER_TICK,
        "conversations": "claude" if claude else "template",
        "llm": {"model": CLAUDE_MODEL, "daily_call_limit": LLM_DAILY_CALL_LIMIT,
                "today": usage.snapshot()} if claude else None,
    }


@app.get("/time")
def get_time(db: Session = Depends(get_db)):
    sim = db.get(SimState, 1)
    return game_time(sim.tick if sim else 0)


@app.get("/map")
def get_map():
    return village_map.to_dict()


# The most rows a list route returns, whatever ?limit= asks for. The routes
# are public and the box has 1 GB: /history?limit=100000000 would load the
# whole table into memory.
MAX_LIST = 100


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIST))


@app.get("/history")
def get_history(limit: int = 50, notable: bool = False, db: Session = Depends(get_db)):
    """Recent events, newest first. copper_change is +/- copper for TRADE rows.

    The tick engine writes only spoken lines and trades now. notable=true
    still filters, for older worlds whose history has a row per villager
    per minute.
    """
    query = db.query(TickHistory)
    if notable:
        query = query.filter(or_(TickHistory.action.in_(("TRADE", "TALK")),
                                 TickHistory.dialogue.isnot(None)))
    rows = query.order_by(TickHistory.id.desc()).limit(_clamp_limit(limit)).all()
    return [
        {"tick": r.tick, "agent_id": r.agent_id,
         "action": r.action, "dialogue": r.dialogue,
         "copper_change": r.gold_change}
        for r in rows
    ]


@app.get("/conversations")
def get_conversations(active: bool = False, limit: int = 10, db: Session = Depends(get_db)):
    """Recent conversations, newest first, with their full transcripts.
    active=true: only the ones still going (the live panel's source).
    At most MAX_LIST, so the scene log reaches back that far."""
    query = db.query(Conversation)
    if active:
        query = query.filter_by(status="active")
    rows = query.order_by(Conversation.id.desc()).limit(_clamp_limit(limit)).all()
    names = {a.id: a.name for a in db.query(AgentState)}
    return [
        {"id": c.id, "a": names.get(c.a_id), "b": names.get(c.b_id),
         "place": c.place, "reason": c.reason, "status": c.status,
         "end_reason": c.end_reason, "started": format_clock(c.started_tick),
         "ended": format_clock(c.ended_tick) if c.ended_tick is not None else None,
         "lines": c.lines or [], "pending_offer": c.pending_offer, "deals": c.deals or [],
         "replans": c.replans or []}
        for c in rows
    ]


# Serve the built frontend (frontend/dist) at "/". Mounted last so the
# API routes above always win; html=True makes "/" serve index.html.
# The dist build is committed to the repo so the deployment box needs
# no Node.js — `git pull` + restart is the whole frontend deploy.
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
