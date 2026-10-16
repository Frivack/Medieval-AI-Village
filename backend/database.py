import logging

from sqlalchemy import create_engine, inspect, text, Column, String, Float, Integer, JSON, DateTime
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


class SimState(Base):
    """World-level state. Single row (id=1) holding the tick counter.

    1 tick = 1 in-game minute; day/hour/minute are derived from tick, not stored.
    """
    __tablename__ = "sim_state"

    id = Column(Integer, primary_key=True, default=1)
    tick = Column(Integer, default=0)


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
