# backend/sim/schedule.py
# What each villager should be doing, and when.
#
# The plan lives in AgentState.daily_plan as JSON:
#   {"days": [3, 4],
#    "blocks": [{"start": 648, "end": 792, "do": "WORK", "at": "Smithy",
#                "with": null, "why": null, "source": "routine", "day": 3}, ...]}
# start/end are absolute ticks (start inclusive, end exclusive), so a block
# can run past midnight (SLEEP 22:00 -> 06:00). Code lays each job's default
# routine day by day ("days" records which days are laid). From stage 3 the
# AI adds blocks of its own (source "ai"); they always win where they
# overlap the routine. Blocks never overlap each other.
from backend.sim.clock import format_clock, game_time, tick_at

WORK, SOCIAL, SLEEP, VISIT = "WORK", "SOCIAL", "SLEEP", "VISIT"
ROUTINE, AI = "routine", "ai"

# Daily template per job: (from_hour, to_hour, activity, place[, why]).
# "work" is the agent's workplace, "home" where they sleep - for now the
# workplace itself (farmhouse, smithy, market stall, inn). A to_hour <=
# from_hour runs past midnight into the next day.
_DAY_JOB = [(6, 18, WORK, "work"), (18, 22, SOCIAL, "Inn"), (22, 6, SLEEP, "home")]
ROUTINES = {
    "Farmer": _DAY_JOB,
    "Blacksmith": _DAY_JOB,
    # The merchant's trading round: buy wheat at the Farm in the morning
    # (67 min walk from the Market), mind the stall, sell at the Inn at night.
    "Merchant": [(6, 9, VISIT, "Farm", "buy wheat for the inn"),
                 (9, 18, WORK, "work"), (18, 22, SOCIAL, "Inn"), (22, 6, SLEEP, "home")],
    # The innkeeper's evening IS work: serving the guests.
    "Innkeeper": [(6, 22, WORK, "work"), (22, 6, SLEEP, "home")],
}


def empty_plan() -> dict:
    return {"days": [], "blocks": []}


def routine_blocks(job: str, workplace: str, day: int) -> list[dict]:
    """The job's default blocks for `day` (the last one may end tomorrow)."""
    places = {"work": workplace, "home": workplace}
    blocks = []
    for from_h, to_h, do, at, *why in ROUTINES[job]:
        end_day = day if to_h > from_h else day + 1
        blocks.append(_block(tick_at(day, from_h), tick_at(end_day, to_h),
                             do, places.get(at, at), why=why[0] if why else None, day=day))
    return blocks


def ensure(plan, job: str, workplace: str, now: int) -> dict:
    """Lay the routine from now through tomorrow and drop finished blocks.

    Returns a new plan; the caller stores it back on the agent. Blocks the
    AI added stay on top: the routine is only laid in the gaps they leave.
    """
    plan = _load(plan)
    today = game_time(now)["day"]
    for day in (today - 1, today, today + 1):   # yesterday's SLEEP runs until 06:00 today
        if day in plan["days"]:
            continue
        routine = routine_blocks(job, workplace, day)
        if max(b["end"] for b in routine) <= now:
            continue                             # that whole day is already over
        for block in routine:
            plan["blocks"] += _gaps(block, [b for b in plan["blocks"] if b["source"] == AI])
        plan["days"].append(day)
    plan["blocks"] = sorted((b for b in plan["blocks"] if b["end"] > now),
                            key=lambda b: b["start"])
    plan["days"] = sorted(d for d in plan["days"] if d >= today - 1)
    return plan


def insert(plan, block: dict) -> dict:
    """Add `block`; it wins, and whatever it overlaps gets cut around it
    (WORK 06-18 + VISIT 07:00-07:30 -> WORK 06-07, VISIT, WORK 07:30-18)."""
    plan = _load(plan)
    kept = []
    for b in plan["blocks"]:
        kept += _cut(b, block["start"], block["end"])
    plan["blocks"] = sorted(kept + [dict(block)], key=lambda b: b["start"])
    return plan


def current(plan, now: int):
    """The block covering tick `now`, or None."""
    for b in _load(plan)["blocks"]:
        if b["start"] <= now < b["end"]:
            return b
    return None


def describe(block) -> dict:
    """API-friendly view of a block, e.g. for the villager cards."""
    return {"do": block["do"], "at": block["at"], "with": block["with"],
            "why": block["why"], "until": format_clock(block["end"])}


def _block(start, end, do, at, with_who=None, why=None, source=ROUTINE, day=None) -> dict:
    return {"start": start, "end": end, "do": do, "at": at,
            "with": with_who, "why": why, "source": source, "day": day}


def _load(plan) -> dict:
    # Rows created before schedules existed hold [] (the column default).
    if not isinstance(plan, dict):
        return empty_plan()
    return {"days": list(plan.get("days", [])),
            "blocks": [dict(b) for b in plan.get("blocks", [])]}


def _cut(block: dict, start: int, end: int) -> list[dict]:
    """The parts of `block` that lie outside [start, end)."""
    if block["end"] <= start or block["start"] >= end:
        return [block]
    parts = []
    if block["start"] < start:
        parts.append({**block, "end": start})
    if block["end"] > end:
        parts.append({**block, "start": end})
    return parts


def _gaps(block: dict, covers: list[dict]) -> list[dict]:
    """The parts of `block` not covered by any block in `covers`."""
    pieces = [block]
    for c in covers:
        pieces = [p for piece in pieces for p in _cut(piece, c["start"], c["end"])]
    return pieces
