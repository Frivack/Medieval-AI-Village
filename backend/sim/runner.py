# backend/sim/runner.py
# Decides WHEN ticks happen; tick_engine decides WHAT one tick does.
#
# Two callers can advance the world: the background loop (server-driven
# time, TICK_INTERVAL_SECONDS > 0) and POST /tick (manual, local dev).
# Both go through one lock so two ticks never run at once — overlapping
# ticks would read the same SimState.tick and write duplicate history.
import asyncio
import logging
import threading
import time

from backend.sim.tick_engine import run_tick

log = logging.getLogger(__name__)

_tick_lock = threading.Lock()


def run_tick_locked() -> dict:
    """run_tick() behind the process-wide tick lock (waits if one is running)."""
    with _tick_lock:
        return run_tick()


async def tick_loop(interval: float, stop: asyncio.Event) -> None:
    """Advance the world every `interval` seconds until `stop` is set.

    Fixed rate measured from each tick's start, with no catch-up: a tick
    slower than the interval is followed by the next one right away, but
    missed ticks are never replayed in a burst (a burst of ticks is a
    burst of paid LLM calls).
    """
    log.info("tick loop started: one tick every %.1f s", interval)
    # The first tick waits one interval: a crash-restart loop under
    # systemd must not fire a tick (= LLM calls) on every restart.
    delay = interval
    while not await _sleep_or_stop(delay, stop):
        started = time.monotonic()
        try:
            # run_tick blocks on SQLite and on LLM HTTP calls. Run on the
            # event loop, it would freeze every API response meanwhile.
            result = await asyncio.to_thread(run_tick_locked)
            log.info("tick %d (day %d %02d:%02d) took %.1f s",
                     result["tick"], result["day"], result["hour"],
                     result["minute"], time.monotonic() - started)
        except Exception:
            # One bad tick must not stop the world. run_tick's session
            # rolls back on error, so the next tick starts clean.
            log.exception("tick failed; the loop keeps running")
        delay = max(0.0, interval - (time.monotonic() - started))
    log.info("tick loop stopped")


async def _sleep_or_stop(seconds: float, stop: asyncio.Event) -> bool:
    """Sleep up to `seconds`; return True as soon as `stop` is set."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
        return True
    except TimeoutError:
        return False
