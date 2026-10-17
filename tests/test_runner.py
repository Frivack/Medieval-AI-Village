# When the tick loop stops using the LLM: after two failed ticks in a row
# it runs ten on the templates, then tries the LLM again — so a tick that
# keeps failing can't keep paying for the same calls.
from backend.sim.runner import TickPolicy


def run(policy, outcomes):
    """Feed tick outcomes (True = ok) through the policy; return which
    ticks were allowed the LLM."""
    used = []
    for ok in outcomes:
        llm = policy.use_llm()
        used.append(llm)
        policy.record(ok=ok, used_llm=llm)
    return used


def test_one_failure_is_retried_with_the_llm():
    assert run(TickPolicy(), [False, True, True]) == [True, True, True]


def test_two_failures_pause_the_llm_for_ten_ticks_then_retry():
    used = run(TickPolicy(), [False, False] + [True] * 10 + [True])
    assert used == [True, True] + [False] * 10 + [True]


def test_a_failure_that_outlasts_the_pause_gets_one_llm_try_per_round():
    # A bug in our own code: every tick fails, with or without the LLM.
    # The failure streak keeps counting through the pause, so after it a
    # single failed LLM tick starts the next pause.
    used = run(TickPolicy(), [False] * 26)
    assert used == [True, True] + [False] * 10 + [True] + [False] * 10 + [True] + [False] * 2
    assert used.count(True) == 4
