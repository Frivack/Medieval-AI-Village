# Building blocks shared by the database tests (the `db` fixture itself
# lives in conftest.py).
from backend.database import AgentState
from backend.sim import schedule
from backend.sim.clock import tick_at

EVENING = tick_at(2, 19)          # SOCIAL time for everyone but the innkeeper


def villager(db, name, job, workplace, inventory=None, wealth=1000, location="Inn", now=EVENING):
    a = AgentState(id=name.lower(), name=name, age=40, job=job, personality="Plain.",
                   wealth=wealth, location=location, workplace=workplace, x=0, y=0, path=[],
                   status="idle", inventory=inventory or {}, needs={"hunger": 0.0},
                   short_term_memory=[],
                   daily_plan=schedule.ensure(None, job, workplace, now))
    db.add(a)
    db.flush()
    return a
