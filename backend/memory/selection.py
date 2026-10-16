# backend/memory/selection.py
# Which memories go into a prompt: recency + importance scoring (mini
# Generative Agents), duplicates collapsed, shown in time order. The vector
# store (when available) adds semantically relevant older memories.
# Moved here from the old per-tick decider; the conversation prompts
# (stage 3 of the CLAUDE.md §6 redesign) are its next user.
from backend.config import MEMORIES_IN_PROMPT, TICKS_PER_HOUR
from backend.memory.store import memory_store
from backend.sim.clock import format_clock

# One importance point outweighs 6 in-game hours of recency — a trade
# (importance 3) stays in the prompt about half a day longer than small
# talk (importance 2) of the same age. Expressed in hours so it survives
# time-scale changes (it was a bare 72 when a tick was 5 minutes).
_RECENCY_PER_IMPORTANCE = 6 * TICKS_PER_HOUR


def memory_lines(agent, now: int, situation: str | None = None) -> list[str]:
    """Prompt lines for the agent's most relevant memories at tick `now`.

    `situation` (e.g. "19:30 at Inn, talking with Edmund") is the vector
    store query; without it only short-term memory is used.
    """
    # Dedupe identical texts keeping the newest occurrence — one evening
    # of repeated greetings would otherwise fill every prompt slot.
    newest = {}
    for m in (agent.short_term_memory or []):
        newest[m["text"]] = m
    scored = sorted(
        newest.values(),
        key=lambda m: m.get("importance", 1) * _RECENCY_PER_IMPORTANCE - (now - m["tick"]),
        reverse=True,
    )[:MEMORIES_IN_PROMPT]
    scored.sort(key=lambda m: m["tick"])
    lines = [f"- [{format_clock(m['tick'])}] {m['text']}" for m in scored]

    if memory_store.enabled and scored and situation:
        seen = {m["text"] for m in scored}
        older = [t for t in memory_store.query(agent.id, situation, k=3)
                 if t not in seen]
        lines += [f"- (earlier) {t}" for t in older]
    return lines
