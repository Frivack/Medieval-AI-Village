# backend/memory/short_term.py
# Writing memories, and picking the ones worth passing on as news.
# A memory is {"tick", "text", "importance" (1-3), "told": [names]}, kept
# in AgentState.short_term_memory (ring buffer) and mirrored to the
# optional vector store.
from backend.config import SHORT_TERM_MEMORY_LIMIT
from backend.memory.store import memory_store

# Memories at least this important are news worth telling others:
# wheat/tool deals (3) and a broken tool (2); not meals, work or chat (1).
NEWS_IMPORTANCE = 2


def remember(agent, tick: int, text: str, importance: int = 1) -> None:
    """Append one observation to the agent's short-term memory and to the
    optional long-term vector store.

    importance (1-3) feeds prompt selection: without it, one evening of
    small talk pushes a day-old trade out of the prompt window (recency
    alone drowns rare-but-important events in frequent chatter).
    """
    memories = list(agent.short_term_memory or [])
    memories.append({"tick": tick, "text": text, "importance": importance})
    # Reassign so SQLAlchemy notices the JSON change.
    agent.short_term_memory = memories[-SHORT_TERM_MEMORY_LIMIT:]
    memory_store.add(agent.id, tick, text)


def news_for(agent, listener_name: str) -> list[dict]:
    """Memories worth telling `listener` that they haven't heard from this
    agent yet, newest first. A memory that mentions the listener isn't news
    to them ("I sold 5 wheat to Gilbert" — Gilbert was there)."""
    return [m for m in reversed(agent.short_term_memory or [])
            if m.get("importance", 1) >= NEWS_IMPORTANCE
            and listener_name not in m.get("told", [])
            and listener_name not in m["text"]]


def mark_told(agent, memory: dict, listener_name: str) -> None:
    """Record that `listener` heard `memory`, so it isn't told twice."""
    memories = [dict(m) for m in agent.short_term_memory or []]
    for m in memories:
        if m["tick"] == memory["tick"] and m["text"] == memory["text"]:
            m["told"] = sorted(set(m.get("told", [])) | {listener_name})
    agent.short_term_memory = memories
