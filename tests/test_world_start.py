# A new world's clock: Day 1 00:00 by default, or the server's local time
# of day with VILLAGE_START_AT_LOCAL_TIME — and never touched again once
# the world exists.
from datetime import datetime

from backend.agents import loader
from backend.database import AgentState, SimState
from backend.sim.clock import format_clock, tick_for_time_of_day


class _At:
    """Stands in for datetime: now() is a fixed local time."""

    def __init__(self, hour, minute):
        self.value = datetime(2026, 10, 17, hour, minute)

    def now(self):
        return self.value


def test_tick_for_time_of_day():
    assert format_clock(tick_for_time_of_day(datetime(2026, 10, 17, 15, 23))) == "Day 1 15:23"
    assert tick_for_time_of_day(datetime(2026, 10, 17, 0, 0)) == 0


def test_a_new_world_starts_at_midnight_by_default(db, monkeypatch):
    monkeypatch.setattr(loader, "START_AT_LOCAL_TIME", False)
    loader.load_agents_from_json(db)
    assert db.query(AgentState).count() == 4
    assert db.get(SimState, 1).tick == 0


def test_a_new_world_can_start_at_local_time_and_keeps_its_clock(db, monkeypatch):
    monkeypatch.setattr(loader, "START_AT_LOCAL_TIME", True)
    monkeypatch.setattr(loader, "datetime", _At(15, 23))
    loader.load_agents_from_json(db)
    assert format_clock(db.get(SimState, 1).tick) == "Day 1 15:23"

    db.get(SimState, 1).tick = 5000                 # the world runs on...
    db.commit()
    monkeypatch.setattr(loader, "datetime", _At(8, 0))
    loader.load_agents_from_json(db)                # ...and a restart leaves it alone
    assert db.get(SimState, 1).tick == 5000
