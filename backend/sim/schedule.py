# backend/sim/schedule.py
# What each villager should be doing, and when.
#
# The plan lives in AgentState.daily_plan as JSON:
#   {"days": [3, 4], "planned": [3],
#    "blocks": [{"start": 648, "end": 792, "do": "WORK", "at": "Smithy",
#                "with": null, "why": null, "source": "routine", "day": 3}, ...]}
# start/end are absolute ticks (start inclusive, end exclusive), so a block
# can run past midnight (SLEEP 22:00 -> 06:00). Code lays each job's default
# routine day by day ("days" records which days are laid). The AI adds
# blocks of its own (source "ai") through apply_ops(); they always win
# where they overlap the routine, and keep what they replaced in "covers"
# so cancelling or moving one gives it back. Blocks never overlap each
# other; a gap is free time. "planned" records the days the villager already planned on
# waking up.
from backend.config import TICKS_PER_DAY
from backend.sim.clock import format_clock, game_time, tick_at

WORK, SOCIAL, SLEEP, VISIT = "WORK", "SOCIAL", "SLEEP", "VISIT"
ACTIVITIES = (WORK, SOCIAL, SLEEP, VISIT)
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

# Limits on what a planner (the AI) may do to a schedule — agreed in the
# CLAUDE.md §6 design: a wide authority, with only sleep guaranteed.
GRID_MINUTES = 5            # its blocks start and end on a 5-minute grid
MAX_OPS = 3                 # per planning call
MAX_APPOINTMENTS = 5        # VISIT blocks "with" someone, at a time
SLEEP_FLOOR_MINUTES = 6 * 60


def empty_plan() -> dict:
    return {"days": [], "planned": [], "blocks": []}


def routine_blocks(job: str, workplace: str, day: int) -> list[dict]:
    """The job's default blocks for `day` (the last one may end tomorrow)."""
    places = {"work": workplace, "home": workplace}
    out = []
    for from_h, to_h, do, at, *why in ROUTINES[job]:
        end_day = day if to_h > from_h else day + 1
        out.append(_block(tick_at(day, from_h), tick_at(end_day, to_h),
                          do, places.get(at, at), why=why[0] if why else None, day=day))
    return out


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
    plan["planned"] = sorted(d for d in plan["planned"] if d >= today - 1)
    return plan


def insert(plan, block: dict) -> dict:
    """Add `block`; it wins, and whatever it overlaps gets cut around it
    (WORK 06-18 + VISIT 07:00-07:30 -> WORK 06-07, VISIT, WORK 07:30-18).
    The cut-away parts go into the new block's "covers"."""
    plan = _load(plan)
    kept, covered = [], []
    for b in plan["blocks"]:
        kept += _cut(b, block["start"], block["end"])
        start, end = max(b["start"], block["start"]), min(b["end"], block["end"])
        if start < end:
            covered.append({**b, "start": start, "end": end})
    plan["blocks"] = sorted(kept + [{**block, "covers": covered}], key=lambda b: b["start"])
    return plan


def blocks(plan) -> list[dict]:
    """The plan's blocks in time order (copies)."""
    return sorted(_load(plan)["blocks"], key=lambda b: b["start"])


def current(plan, now: int):
    """The block covering tick `now`, or None (free time)."""
    for b in _load(plan)["blocks"]:
        if b["start"] <= now < b["end"]:
            return b
    return None


def describe(block) -> dict:
    """API-friendly view of a block, e.g. for the villager cards."""
    return {"do": block["do"], "at": block["at"], "with": block["with"],
            "why": block["why"], "until": format_clock(block["end"])}


def block_id(block) -> str:
    """Stable handle a planner can name: blocks never share a start tick."""
    return f"b{block['start']}"


def for_planner(plan, now: int) -> list[dict]:
    """The blocks still ahead (or in progress), as a planner sees them."""
    return [{"id": block_id(b), "from": format_clock(b["start"]), "to": format_clock(b["end"]),
             "do": b["do"], "at": b["at"], "with": b["with"], "why": b["why"],
             "routine": b["source"] == ROUTINE}
            for b in blocks(plan) if b["end"] > now]


def is_planned(plan, day: int) -> bool:
    return day in _load(plan)["planned"]


def mark_planned(plan, day: int) -> dict:
    plan = _load(plan)
    plan["planned"] = sorted(set(plan["planned"]) | {day})
    return plan


def apply_ops(plan, ops, now: int, *, workplace: str, places, people) -> tuple[dict, list, list]:
    """Apply a planner's schedule edits, each validated on its own.

    ops: [{"op": "insert", "day", "from": "HH:MM", "to": "HH:MM", "do", "at",
           "with", "why"} | {"op": "cancel", "block": id}
          | {"op": "move", "block": id, "day", "from", "to"}]
    Returns (plan, applied, rejected) with a short reason per op. An op is
    rejected (and skipped) if it names an unknown place/person/block, falls
    off the 5-minute grid, lies outside now..end of tomorrow, sends WORK
    away from the workplace, books more than MAX_APPOINTMENTS, or leaves a
    night with less than SLEEP_FLOOR_MINUTES of sleep.
    """
    plan = _load(plan)
    applied, rejected = [], []
    for i, op in enumerate(ops or []):
        if i >= MAX_OPS:
            rejected.append(f"{_label(op)}: more than {MAX_OPS} changes at once")
            continue
        candidate, why_not = _apply_one(plan, op, now, workplace, set(places), set(people))
        if why_not is None:
            why_not = _limits_problem(candidate, now)
        if why_not:
            rejected.append(f"{_label(op)}: {why_not}")
        else:
            plan = candidate
            applied.append(_label(op))
    return plan, applied, rejected


def _apply_one(plan, op, now, workplace, places, people):
    if not isinstance(op, dict):
        return plan, "not an edit"
    kind = op.get("op")
    if kind == "insert":
        span, why_not = _span(op, now)
        if why_not:
            return plan, why_not
        block, why_not = _new_block(op, span, workplace, places, people)
        return (plan, why_not) if why_not else (insert(plan, block), None)
    if kind in ("cancel", "move"):
        target = next((b for b in plan["blocks"]
                       if block_id(b) == op.get("block") and b["end"] > now), None)
        if target is None:
            return plan, f"no upcoming block {op.get('block')!r}"
        rest = _uncover({**plan, "blocks": [b for b in plan["blocks"] if b is not target]}, target)
        if kind == "cancel":
            return rest, None
        span, why_not = _span(op, now)
        if why_not:
            return plan, why_not
        return insert(rest, {**target, "start": span[0], "end": span[1], "source": AI}), None
    return plan, f"unknown edit {kind!r}"


def _uncover(plan, gone: dict) -> dict:
    """`gone` was cancelled or moved away: what it had replaced comes back
    wherever nothing else has taken its place since. A routine block
    covers nothing, so cancelling one leaves free time."""
    back = [p for c in gone.get("covers", []) for p in _gaps(c, plan["blocks"])]
    return {**plan, "blocks": sorted(plan["blocks"] + back, key=lambda b: b["start"])}


def _span(op, now):
    """(start, end) ticks for an op's day/from/to, or a reason it's invalid."""
    try:
        day = int(op["day"])
        (fh, fm), (th, tm) = (_hhmm(op["from"]), _hhmm(op["to"]))
    except (KeyError, TypeError, ValueError):
        return None, "needs day, from and to (HH:MM)"
    if fm % GRID_MINUTES or tm % GRID_MINUTES:
        return None, f"times must be on a {GRID_MINUTES}-minute grid"
    start, end = tick_at(day, fh, fm), tick_at(day, th, tm)
    if end <= start:
        end += TICKS_PER_DAY                       # runs past midnight
    today = game_time(now)["day"]
    if start < now:
        return None, "starts in the past"
    if end > tick_at(today + 2, 0):
        return None, "goes beyond the end of tomorrow"
    return (start, end), None


def _hhmm(text: str) -> tuple[int, int]:
    h, m = (int(x) for x in str(text).split(":"))
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return h, m


def _new_block(op, span, workplace, places, people):
    do, at, who = op.get("do"), op.get("at"), op.get("with")
    if do not in ACTIVITIES:
        return None, f"unknown activity {do!r}"
    if at not in places:
        return None, f"unknown place {at!r}"
    if do == WORK and at != workplace:
        return None, f"work happens at {workplace}"
    if who is not None and who not in people:
        return None, f"unknown person {who!r}"
    why = op.get("why") if isinstance(op.get("why"), str) else None
    return _block(span[0], span[1], do, at, with_who=who, why=why, source=AI), None


def _limits_problem(plan, now: int):
    """What a candidate plan breaks, if anything: appointments, sleep."""
    appointments = [b for b in plan["blocks"] if b["do"] == VISIT and b["with"] and b["end"] > now]
    if len(appointments) > MAX_APPOINTMENTS:
        return f"more than {MAX_APPOINTMENTS} appointments"
    today = game_time(now)["day"]
    for day in (today, today + 1):                 # tonight's and tomorrow night's sleep
        lo, hi = tick_at(day, 12), tick_at(day + 1, 12)
        slept = sum(max(0, min(b["end"], hi) - max(b["start"], lo))
                    for b in plan["blocks"] if b["do"] == SLEEP)
        if slept < SLEEP_FLOOR_MINUTES:
            return f"leaves only {slept // 60}h{slept % 60:02d} of sleep the night after day {day}"
    return None


def _label(op) -> str:
    if not isinstance(op, dict):
        return "?"
    if op.get("op") == "insert":
        who = f" with {op.get('with')}" if op.get("with") else ""
        return f"insert {op.get('do')} at {op.get('at')}{who} {op.get('from')}-{op.get('to')} day {op.get('day')}"
    return f"{op.get('op')} {op.get('block')}"


def _block(start, end, do, at, with_who=None, why=None, source=ROUTINE, day=None) -> dict:
    return {"start": start, "end": end, "do": do, "at": at,
            "with": with_who, "why": why, "source": source, "day": day}


def _load(plan) -> dict:
    # Rows created before schedules existed hold [] (the column default).
    if not isinstance(plan, dict):
        return empty_plan()
    return {"days": list(plan.get("days", [])),
            "planned": list(plan.get("planned", [])),
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
