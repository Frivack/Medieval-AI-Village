# Unit tests for backend/sim/schedule.py — pure functions, no database.
# Run from the repo root:  python -m pytest
import pytest

from backend.sim import schedule
from backend.sim.clock import tick_at


def farmer_plan(now):
    return schedule.ensure(None, "Farmer", "Farm", now)


def doing(plan, day, hour, minute=0):
    block = schedule.current(plan, tick_at(day, hour, minute))
    return (block["do"], block["at"]) if block else None


def test_farmer_routine_over_a_day():
    plan = farmer_plan(tick_at(2, 6))
    assert doing(plan, 2, 7) == ("WORK", "Farm")
    assert doing(plan, 2, 19) == ("SOCIAL", "Inn")
    assert doing(plan, 2, 23, 30) == ("SLEEP", "Farm")       # sleeps at home
    assert doing(plan, 3, 3) == ("SLEEP", "Farm")            # the block runs past midnight


def test_first_night_is_covered():
    # Tick 0 is Day 1 00:00: yesterday's (day 0) sleep block must cover it.
    assert doing(farmer_plan(0), 1, 0) == ("SLEEP", "Farm")


def test_innkeeper_works_through_the_evening():
    plan = schedule.ensure(None, "Innkeeper", "Inn", tick_at(1, 6))
    assert doing(plan, 1, 20) == ("WORK", "Inn")
    assert doing(plan, 1, 22, 30) == ("SLEEP", "Inn")


def test_ensure_lays_tomorrow_and_drops_finished_blocks():
    now = tick_at(2, 12)
    plan = farmer_plan(now)
    assert all(b["end"] > now for b in plan["blocks"])
    assert plan["days"] == [2, 3]
    assert doing(plan, 3, 7) == ("WORK", "Farm")


def test_ensure_is_idempotent():
    now = tick_at(2, 12)
    assert schedule.ensure(farmer_plan(now), "Farmer", "Farm", now) == farmer_plan(now)


def test_old_rows_with_a_list_plan_still_work():
    # AgentState.daily_plan defaulted to [] before schedules existed.
    assert doing(schedule.ensure([], "Farmer", "Farm", tick_at(1, 7)), 1, 7) == ("WORK", "Farm")


def test_insert_wins_and_splits_the_block_it_overlaps():
    plan = farmer_plan(tick_at(2, 6))
    visit = schedule._block(tick_at(2, 7), tick_at(2, 7, 30), "VISIT", "Smithy",
                            with_who="Edmund", source=schedule.AI)
    plan = schedule.insert(plan, visit)
    assert doing(plan, 2, 6, 30) == ("WORK", "Farm")
    assert doing(plan, 2, 7, 10) == ("VISIT", "Smithy")
    assert doing(plan, 2, 7, 30) == ("WORK", "Farm")
    blocks = sorted(plan["blocks"], key=lambda b: b["start"])
    assert all(a["end"] <= b["start"] for a, b in zip(blocks, blocks[1:]))  # no overlaps


def test_routine_is_laid_around_an_ai_block_on_a_later_day():
    plan = farmer_plan(tick_at(2, 12))                     # days 2 and 3 laid
    errand = schedule._block(tick_at(4, 8), tick_at(4, 9), "VISIT", "Market",
                             source=schedule.AI)
    plan = schedule.insert(plan, errand)                    # day 4 not laid yet
    plan = schedule.ensure(plan, "Farmer", "Farm", tick_at(3, 12))  # now lays day 4
    assert doing(plan, 4, 7, 30) == ("WORK", "Farm")
    assert doing(plan, 4, 8, 30) == ("VISIT", "Market")     # the AI block survived
    assert doing(plan, 4, 9, 30) == ("WORK", "Farm")


def test_describe_for_the_api():
    block = schedule.current(farmer_plan(tick_at(1, 6)), tick_at(1, 7))
    assert schedule.describe(block) == {"do": "WORK", "at": "Farm", "with": None,
                                        "why": None, "until": "Day 1 18:00"}


# --- planner edits (apply_ops) ------------------------------------------------

PLACES = ["Farm", "Smithy", "Market", "Inn"]
NOW = tick_at(3, 6)


def edit(plan, *ops, now=NOW):
    return schedule.apply_ops(plan, list(ops), now, workplace="Farm",
                              places=PLACES, people=["Edmund", "Gilbert", "Margaret"])


def visit(frm, to, day=3, **extra):
    return {"op": "insert", "day": day, "from": frm, "to": to, "do": "VISIT", "at": "Market", **extra}


@pytest.mark.parametrize("op, reason", [
    (visit("05:00", "05:30"), "starts in the past"),
    (visit("10:00", "11:00", day=5), "beyond the end of tomorrow"),
    (visit("10:02", "11:00"), "5-minute grid"),
    (visit("10:00", "11:00", at="Castle"), "unknown place"),
    (visit("10:00", "11:00", **{"with": "Merlin"}), "unknown person"),
    ({**visit("10:00", "11:00"), "do": "WORK"}, "work happens at Farm"),
    ({**visit("10:00", "11:00"), "do": "DANCE"}, "unknown activity"),
    ({"op": "cancel", "block": "b1"}, "no upcoming block"),
    ({"op": "teleport"}, "unknown edit"),
    ({"op": "insert", "day": 3}, "needs day, from and to"),
])
def test_bad_edits_are_rejected_and_change_nothing(op, reason):
    plan = farmer_plan(NOW)
    new, applied, rejected = edit(plan, op)
    assert applied == [] and len(rejected) == 1 and reason in rejected[0]
    assert schedule.blocks(new) == schedule.blocks(plan)


def test_at_most_three_edits_per_call():
    _, applied, rejected = edit(farmer_plan(NOW), *(visit(f"1{i}:00", f"1{i}:30") for i in range(4)))
    assert len(applied) == 3 and "more than 3 changes" in rejected[0]


def test_at_most_five_appointments():
    plan = farmer_plan(NOW)
    for day, hours in ((3, (8, 10, 12)), (4, (8, 10))):
        for h in hours:
            plan, applied, _ = edit(plan, visit(f"{h}:00", f"{h}:30", day=day, **{"with": "Gilbert"}))
            assert applied
    _, applied, rejected = edit(plan, visit("14:00", "14:30", **{"with": "Gilbert"}))
    assert applied == [] and "more than 5 appointments" in rejected[0]


def test_sleep_can_shrink_to_six_hours_but_not_less():
    plan = farmer_plan(NOW)
    late = {"op": "insert", "day": 3, "from": "22:00", "to": "00:00", "do": "SOCIAL", "at": "Inn"}
    plan, applied, _ = edit(plan, late)                       # 8h -> 6h of sleep: allowed
    assert applied and doing(plan, 3, 23) == ("SOCIAL", "Inn") and doing(plan, 4, 1) == ("SLEEP", "Farm")
    later = {**late, "from": "00:00", "to": "00:30", "day": 4}
    _, applied, rejected = edit(plan, later)                  # 5h30: rejected
    assert applied == [] and "sleep" in rejected[0]


def test_cancelling_an_added_block_gives_the_routine_back():
    plan, _, _ = edit(farmer_plan(NOW), visit("10:00", "10:30"))
    block = next(b for b in schedule.for_planner(plan, NOW) if b["do"] == "VISIT")
    plan, applied, _ = edit(plan, {"op": "cancel", "block": block["id"]})
    assert applied and doing(plan, 3, 10, 10) == ("WORK", "Farm")
    work = next(b for b in schedule.for_planner(plan, NOW) if b["do"] == "WORK")
    plan, applied, _ = edit(plan, {"op": "cancel", "block": work["id"]})
    assert applied and doing(plan, 3, 7) is None          # a routine block: free time


def test_move_reschedules_a_block_as_the_planners_own():
    plan, _, _ = edit(farmer_plan(NOW), visit("10:00", "10:30", why="buy food"))
    block = next(b for b in schedule.for_planner(plan, NOW) if b["do"] == "VISIT")
    plan, applied, _ = edit(plan, {"op": "move", "block": block["id"], "day": 3,
                                   "from": "15:00", "to": "15:30"})
    assert applied and doing(plan, 3, 10, 10) == ("WORK", "Farm")
    moved = schedule.current(plan, tick_at(3, 15, 10))
    assert (moved["do"], moved["why"], moved["source"]) == ("VISIT", "buy food", schedule.AI)


def test_planned_days_are_remembered_and_pruned():
    plan = schedule.mark_planned(farmer_plan(NOW), 3)
    assert schedule.is_planned(plan, 3) and not schedule.is_planned(plan, 4)
    later = schedule.ensure(plan, "Farmer", "Farm", tick_at(6, 6))
    assert not schedule.is_planned(later, 3)
