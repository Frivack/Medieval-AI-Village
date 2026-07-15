# backend/sim/clock.py
# In-game time helpers. Lives in its own module (not tick_engine) so that
# decider can format memory timestamps without importing tick_engine,
# which would be a circular import (tick_engine imports decider).
from backend.config import TICKS_PER_DAY, TICKS_PER_HOUR, MINUTES_PER_TICK


def game_time(tick: int) -> dict:
    day_tick = tick % TICKS_PER_DAY
    return {
        "tick": tick,
        "day": tick // TICKS_PER_DAY + 1,
        "hour": day_tick // TICKS_PER_HOUR,
        "minute": (day_tick % TICKS_PER_HOUR) * MINUTES_PER_TICK,
    }


def format_clock(tick: int) -> str:
    t = game_time(tick)
    return f"Day {t['day']} {t['hour']:02d}:{t['minute']:02d}"
