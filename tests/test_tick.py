# Whole ticks on a throwaway world: what the tick engine leaves behind.
import pytest
from sqlalchemy.orm import sessionmaker

from backend.agents.loader import load_agents_from_json
from backend.database import AgentState, SimState, TickHistory
from backend.sim import tick_engine
from backend.sim.clock import tick_at
from backend.world.map import village_map
from backend.world.tiles import TileType


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


def test_spots_are_distinct_floor_tiles():
    for b in village_map.buildings.values():
        assert len(b.spots) == len(set(b.spots)) >= 4, b.name
        assert all(village_map.tile_at(x, y) == TileType.FLOOR for x, y in b.spots), b.name


def test_everyone_at_the_inn_stands_on_their_own_tile(world):
    world.get(SimState, 1).tick = tick_at(1, 17, 55)
    world.commit()
    for _ in range(65):                    # 18:00 everyone heads for the Inn; Farm is 48 min away
        tick_engine.run_tick(use_llm=False)
    world.expire_all()
    agents = world.query(AgentState).all()
    assert {a.location for a in agents} == {"Inn"}
    assert len({(a.x, a.y) for a in agents}) == len(agents)
