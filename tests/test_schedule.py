# Unit tests for backend/sim/schedule.py — pure functions, no database.
# Run from the repo root:  python -m pytest
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
