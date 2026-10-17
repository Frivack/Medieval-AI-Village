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


class TickPolicy:
    """Whether the next tick may use the LLM.

    A tick is one transaction: if it fails after the Claude calls were made
    (a bug in what follows, a locked database at commit), all of it rolls
    back and the next tick meets the same situation and pays for the same
    calls again — every minute, for as long as the cause lasts. So after
    FAILURES_BEFORE_PAUSE failed ticks in a row the next TEMPLATE_TICKS run
    on the templates: if the trouble came from a model's answer the world
    moves past it, and if it's a bug in our code it costs nothing while it
    lasts. Then the LLM gets another try.
    """
    FAILURES_BEFORE_PAUSE = 2
    TEMPLATE_TICKS = 10

    def __init__(self):
        self.failures = 0          # failed ticks in a row
        self.template_left = 0     # ticks still to run without the LLM

    def use_llm(self) -> bool:
        return self.template_left == 0

    def record(self, ok: bool, used_llm: bool) -> None:
        if not used_llm:
            self.template_left -= 1
        if ok:
            self.failures = 0
            return
        self.failures += 1
        if used_llm and self.failures >= self.FAILURES_BEFORE_PAUSE:
            self.template_left = self.TEMPLATE_TICKS
            log.error("%d ticks failed in a row: the next %d run without the LLM",
                      self.failures, self.TEMPLATE_TICKS)


def run_tick_locked(use_llm: bool = True) -> dict:
    """run_tick() behind the process-wide tick lock (waits if one is running)."""
    with _tick_lock:
        return run_tick(use_llm)


async def tick_loop(interval: float, stop: asyncio.Event) -> None:
    """Advance the world every `interval` seconds until `stop` is set.

    Fixed rate measured from each tick's start, with no catch-up: a tick
    slower than the interval is followed by the next one right away, but
    missed ticks are never replayed in a burst (a burst of ticks is a
    burst of paid LLM calls).
    """
    log.info("tick loop started: one tick every %.1f s", interval)
    policy = TickPolicy()
    # The first tick waits one interval: a crash-restart loop under
    # systemd must not fire a tick (= LLM calls) on every restart.
    delay = interval
    while not await _sleep_or_stop(delay, stop):
        started = time.monotonic()
        use_llm = policy.use_llm()
        try:
            # run_tick blocks on SQLite and on LLM HTTP calls. Run on the
            # event loop, it would freeze every API response meanwhile.
            result = await asyncio.to_thread(run_tick_locked, use_llm)
            policy.record(ok=True, used_llm=use_llm)
            log.info("tick %d (day %d %02d:%02d) took %.1f s%s",
                     result["tick"], result["day"], result["hour"], result["minute"],
                     time.monotonic() - started, "" if use_llm else " (templates)")
        except Exception:
            # One bad tick must not stop the world. run_tick's session
            # rolls back on error, so the next tick starts clean.
            log.exception("tick failed; the loop keeps running")
            policy.record(ok=False, used_llm=use_llm)
        delay = max(0.0, interval - (time.monotonic() - started))
    log.info("tick loop stopped")


async def _sleep_or_stop(seconds: float, stop: asyncio.Event) -> bool:
    """Sleep up to `seconds`; return True as soon as `stop` is set."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
        return True
    except TimeoutError:
        return False
