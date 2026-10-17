# The daily call limit has to survive a restart: the tick engine saves
# usage.snapshot() in SimState.llm_usage, and startup restores it.
from types import SimpleNamespace

import pytest

from backend import main
from backend.database import SimState
from backend.llm import claude, usage


@pytest.fixture(autouse=True)
def fresh():
    usage.reset()
    claude.reset_breaker()
    yield
    usage.reset()


def test_todays_snapshot_comes_back_after_a_restart():
    usage.record("claude-opus-5-5", SimpleNamespace(input_tokens=100, output_tokens=10,
                                                    cache_creation_input_tokens=0,
                                                    cache_read_input_tokens=0))
    usage.record_failure()
    saved = usage.snapshot()
    usage.reset()                                   # the process restarts
    assert usage.calls_today() == 0
    usage.restore(saved)
    assert usage.calls_today() == 2 and usage.snapshot() == saved


def test_a_snapshot_from_another_day_is_ignored():
    usage.restore({"date": "2000-01-01", "calls": 400, "failures": 0})
    usage.restore(None)                             # rows from before this column
    assert usage.calls_today() == 0


def test_the_limit_holds_across_a_restart(db, monkeypatch):
    # 499 calls were made before the restart and saved with the last tick.
    db.add(SimState(id=1, tick=10, llm_usage={**usage.snapshot(), "calls": 499}))
    db.commit()
    main.restore_llm_usage(db)                      # what startup does
    monkeypatch.setattr(claude, "LLM_DAILY_CALL_LIMIT", 499)
    with pytest.raises(claude.ClaudeUnavailable, match="daily limit"):
        claude._ask("system", "user", {"type": "object"}, 16)
