import logging

from sqlalchemy import (create_engine, inspect, text, Column, String, Float, Integer,
                        JSON, DateTime, UniqueConstraint)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from backend.config import DB_PATH

log = logging.getLogger(__name__)

Base = declarative_base()


class AgentState(Base):
    __tablename__ = "agent_states"

    id = Column(String, primary_key=True)
    name = Column(String)
    age = Column(Integer)
    job = Column(String)
    personality = Column(String)
    wealth = Column(Integer, default=0)
    location = Column(String)
    workplace = Column(String)
    x = Column(Integer, default=0)
    y = Column(Integer, default=0)
    path = Column(JSON, default=list)  # remaining A* steps: [[x, y], ...]
    status = Column(String, default="idle")
    inventory = Column(JSON)
    daily_plan = Column(JSON, default=list)
    # Bodily/working needs, e.g. {"hunger": 40.0, "tool": 80}; rules and
    # defaults in backend/sim/economy.py. NULL on rows from before 1b.
    needs = Column(JSON, default=dict)
    short_term_memory = Column(JSON, default=list)
    talking_to = Column(String, nullable=True)
    updated_at  = Column(DateTime, default=datetime.now)


class TickHistory(Base):
    __tablename__ = "tick_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tick = Column(Integer)
    agent_id = Column(String)
    action = Column(String)
    dialogue = Column(String)
    gold_change = Column(Float, default=0.0)  # in copper (name predates the copper economy)
    created_at = Column(DateTime, default=datetime.now)


class Conversation(Base):
    """A 1:1 conversation, one line per tick (backend/sim/conversation.py).

    `a_id` started it for `reason` (trade | appointment | news | chat), with
    details in `topic`. `lines` is the transcript: [{"tick", "speaker",
    "text", "offer", "response"}]. `pending_offer` is the latest unanswered
    offer {"by", "kind": "buy"|"sell", "item", "quantity", "price"};
    `deals` the trades it settled.
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    a_id = Column(String)
    b_id = Column(String)
    place = Column(String)
    reason = Column(String)
    topic = Column(JSON, default=dict)
    started_tick = Column(Integer)
    ended_tick = Column(Integer, nullable=True)
    status = Column(String, default="active")   # active | ended
    end_reason = Column(String, nullable=True)
    next_speaker_id = Column(String)
    lines = Column(JSON, default=list)
    pending_offer = Column(JSON, nullable=True)
    deals = Column(JSON, default=list)
    # What each side made of it afterwards: [{"who", "applied", "rejected",
    # "memory", "affinity"}] (schedule edits applied/rejected by validation).
    replans = Column(JSON, default=list)


class Relationship(Base):
    """How `agent_id` feels about `other_id` — one row per direction, since
    A liking B says nothing about B liking A. `last_talk_tick` drives the
    per-pair conversation cooldown."""
    __tablename__ = "relationships"
    __table_args__ = (UniqueConstraint("agent_id", "other_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String)
    other_id = Column(String)
    affinity = Column(Integer, default=0)       # -30 (hostile) .. +30 (close); see conversation.py
    last_talk_tick = Column(Integer, nullable=True)


class SimState(Base):
    """World-level state. Single row (id=1) holding the tick counter.

    1 tick = 1 in-game minute; day/hour/minute are derived from tick, not stored.
    """
    __tablename__ = "sim_state"

    id = Column(Integer, primary_key=True, default=1)
    tick = Column(Integer, default=0)
    # Today's LLM usage (backend/llm/usage.py snapshot), saved with each tick
    # so the daily call limit survives a restart. NULL on older rows.
    llm_usage = Column(JSON, nullable=True)


engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
    add_missing_columns(engine, Base.metadata)


def add_missing_columns(bind, metadata) -> list[str]:
    """Additive-only schema migration.

    create_all() creates missing TABLES but never alters existing ones, so
    a column added to a model would make every query on an older
    village.db fail. Add such columns in place (old rows get NULL, which
    the code must treat as "default") — the world survives a deploy
    instead of being reset. Renames, type changes and drops are NOT
    handled here; those still need a deliberate migration.
    Returns the "table.column" names it added.
    """
    added = []
    existing_tables = set(inspect(bind).get_table_names())
    with bind.begin() as conn:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all just made it, complete
            have = {c["name"] for c in inspect(conn).get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl_type = column.type.compile(dialect=bind.dialect)
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'))
                added.append(f"{table.name}.{column.name}")
    for name in added:
        log.info("schema: added column %s", name)
    return added


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
