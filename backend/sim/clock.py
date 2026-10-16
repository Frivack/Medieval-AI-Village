# backend/sim/clock.py
# In-game time helpers. Lives in its own module (not tick_engine) so that
# memory selection and schedules can use them without importing
# tick_engine, which would be a circular import.
from backend.config import TICKS_PER_DAY, TICKS_PER_HOUR, MINUTES_PER_TICK


def game_time(tick: int) -> dict:
    day_tick = tick % TICKS_PER_DAY
    return {
        "tick": tick,
        "day": tick // TICKS_PER_DAY + 1,
        "hour": day_tick // TICKS_PER_HOUR,
        "minute": (day_tick % TICKS_PER_HOUR) * MINUTES_PER_TICK,
    }


def tick_at(day: int, hour: int, minute: int = 0) -> int:
    """Inverse of game_time: the tick at which `day hour:minute` begins.
    Day 1 00:00 is tick 0; earlier days give negative ticks."""
    return (day - 1) * TICKS_PER_DAY + hour * TICKS_PER_HOUR + minute // MINUTES_PER_TICK


def format_clock(tick: int) -> str:
    t = game_time(tick)
    return f"Day {t['day']} {t['hour']:02d}:{t['minute']:02d}"
