# backend/llm/usage.py
# Today's LLM calls, tokens and estimated cost (it resets when the UTC date
# changes). Feeds the daily call limit (config.LLM_DAILY_CALL_LIMIT) and
# GET /status. Counted in memory; the tick engine saves a snapshot with
# every tick and startup restores it, so a restart doesn't reset the limit.
# The tick loop's thread writes and API requests read, hence the lock.
import threading
from datetime import datetime, timezone

# $ per million tokens (input, output, cache read), first-party API rates
# as of 2026-10 (claude-api skill). 5-minute cache writes cost 1.25x input
# on all three; cache reads are 0.1x input on Haiku and Sonnet 5.5 but
# 0.05x on Opus 5.5 — a flat 0.1x overstated Opus by ~5%.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
}
CACHE_WRITE = 1.25

_lock = threading.Lock()
_today = None
_stats = {}


def _fresh() -> dict:
    return {"calls": 0, "failures": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0}


def _roll() -> None:
    global _today, _stats
    day = datetime.now(timezone.utc).date().isoformat()
    if day != _today:
        _today, _stats = day, _fresh()


def record(model: str, usage) -> float:
    """Count one successful call; returns its estimated cost in USD."""
    price_in, price_out, price_read = PRICES.get(model, (0.0, 0.0, 0.0))
    fresh_in = getattr(usage, "input_tokens", 0) or 0
    write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cost = ((fresh_in + write * CACHE_WRITE) * price_in + read * price_read + out * price_out) / 1e6
    with _lock:
        _roll()
        _stats["calls"] += 1
        _stats["input_tokens"] += fresh_in + write + read
        _stats["output_tokens"] += out
        _stats["cache_read_tokens"] += read
        _stats["cache_write_tokens"] += write
        _stats["cost_usd"] += cost
    return cost


def record_failure() -> None:
    with _lock:
        _roll()
        _stats["failures"] += 1


def calls_today() -> int:
    with _lock:
        _roll()
        return _stats["calls"] + _stats["failures"]


def snapshot() -> dict:
    with _lock:
        _roll()
        return {"date": _today, **_stats, "cost_usd": round(_stats["cost_usd"], 6)}


def restore(saved) -> None:
    """Pick up today's counts after a restart, from a snapshot() the tick
    engine stored with the last tick (SimState.llm_usage). Without this a
    restart — a deploy, systemd's Restart=on-failure, an OOM kill — would
    start the daily call limit from zero again. A snapshot from another
    (UTC) day is ignored."""
    global _stats
    with _lock:
        _roll()
        if not isinstance(saved, dict) or saved.get("date") != _today:
            return
        fresh = _fresh()
        _stats = {k: type(fresh[k])(saved.get(k) or 0) for k in fresh}


def reset() -> None:
    """For tests and the simulator."""
    global _today
    with _lock:
        _today = None
        _roll()
