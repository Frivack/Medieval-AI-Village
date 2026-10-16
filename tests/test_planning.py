# The wake-up planner in the tick engine: once per day, right after the
# sleep block ends, a planner may edit the day's schedule.
import pytest

from backend.sim import conversation, schedule, speech, tick_engine
from backend.sim.clock import game_time, tick_at
from tests.helpers import villager

DAWN = tick_at(3, 6)              # the farmer's sleep block ends now


@pytest.fixture
def thomas(db):
    t = villager(db, "Thomas", "Farmer", "Farm", location="Farm", now=DAWN - 1)
    t.status = "resting"          # he slept through the night
    return t


def step(db, agent, now, monkeypatch, planner):
    calls = []

    def counting(view):
        calls.append(view)
        return planner(view)

    monkeypatch.setattr(tick_engine, "PLAN", counting)
    entry = tick_engine._step_agent(db, agent, [agent], {agent.id: agent}, game_time(now),
                                    conversation.Relations(db), set())
    return entry, calls


def test_waking_up_plans_the_day_and_templates_keep_the_routine(db, thomas, monkeypatch):
    before = schedule.for_planner(thomas.daily_plan, DAWN)
    entry, calls = step(db, thomas, DAWN, monkeypatch, speech.template_replan)
    assert entry["detail"] == "woke up and planned the day: kept the routine"
    assert thomas.status == "planning" and schedule.is_planned(thomas.daily_plan, 3)
    assert calls[0]["event"] == "wake_up" and calls[0]["schedule"][0]["do"] == "WORK"
    assert schedule.for_planner(thomas.daily_plan, DAWN) == before

    entry, calls = step(db, thomas, DAWN + 1, monkeypatch, speech.template_replan)
    assert entry["action"] == "WORK" and calls == []


def test_no_planning_while_asleep_or_twice_a_day(db, thomas, monkeypatch):
    entry, calls = step(db, thomas, DAWN - 30, monkeypatch, speech.template_replan)
    assert entry["action"] == "REST" and calls == []

    step(db, thomas, DAWN, monkeypatch, speech.template_replan)
    thomas.status = "resting"     # e.g. a nap: still only one plan per day
    entry, calls = step(db, thomas, DAWN + 5, monkeypatch, speech.template_replan)
    assert calls == [] and entry["action"] == "WORK"


def test_a_wake_up_plan_is_validated_and_applied(db, thomas, monkeypatch):
    def planner(view):
        tonight = next(b for b in view["schedule"]
                       if b["do"] == "SLEEP" and b["from"] == "Day 3 22:00")
        return {"change": True, "affinity": 0,
                "memory": {"text": "I need to buy food at the market today.", "importance": 2},
                "ops": [{"op": "insert", "day": 3, "from": "12:00", "to": "12:30",
                         "do": "VISIT", "at": "Market", "why": "buy food"},
                        {"op": "cancel", "block": tonight["id"]}]}   # no sleep: rejected

    entry, _ = step(db, thomas, DAWN, monkeypatch, planner)
    assert entry["plan"]["applied"] == ["insert VISIT at Market 12:00-12:30 day 3"]
    assert "sleep" in entry["plan"]["rejected"][0]
    assert schedule.current(thomas.daily_plan, tick_at(3, 12, 10))["at"] == "Market"
    assert schedule.current(thomas.daily_plan, tick_at(3, 23))["do"] == "SLEEP"
    assert thomas.short_term_memory[-1]["text"] == "I need to buy food at the market today."


def test_a_cancelled_block_leaves_free_time(db, thomas, monkeypatch):
    def planner(view):
        work = view["schedule"][0]
        return {"change": True, "ops": [{"op": "cancel", "block": work["id"]}],
                "memory": None, "affinity": 0}

    step(db, thomas, DAWN, monkeypatch, planner)
    entry, _ = step(db, thomas, DAWN + 1, monkeypatch, planner)
    assert entry["detail"] == "free time at Farm" and thomas.status == "idle"
