# Whole ticks on a throwaway world: what the tick engine leaves behind.
import pytest
from sqlalchemy.orm import sessionmaker

from backend.agents.loader import load_agents_from_json
from backend.database import SimState, TickHistory
from backend.sim import tick_engine
from backend.sim.clock import tick_at


@pytest.fixture
def world(db, monkeypatch):
    """The four villagers at their workplaces, Day 1 06:00 — the Merchant
    sets off to buy wheat at the Farm. run_tick opens its own sessions, so
    point it at the test database."""
    load_agents_from_json(db)
    db.get(SimState, 1).tick = tick_at(1, 6, 0)
    db.commit()
    monkeypatch.setattr(tick_engine, "SessionLocal", sessionmaker(bind=db.get_bind()))
    return db


def test_history_keeps_only_lines_and_trades(world):
    for _ in range(150):                   # to 08:30: walk to the Farm, haggle, buy
        tick_engine.run_tick(use_llm=False)
    actions = {a for (a,) in world.query(TickHistory.action).distinct()}
    assert "TALK" in actions and "TRADE" in actions
    assert actions <= {"TALK", "TRADE"}    # no rows for walking, working, sleeping
