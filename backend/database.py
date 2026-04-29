from sqlalchemy import create_engine, Column, String, Float, Integer, JSON, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from pathlib import Path

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
    status = Column(String, default="idle")
    inventory = Column(JSON)
    daily_plan = Column(JSON, default=list)
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
    gold_change = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)


BASE_DIR = Path(__file__).parent.parent  # backend/ → Medieval-AI-Village/
DB_PATH = BASE_DIR / "data" / "village.db"

engine = create_engine(f"sqlite:///{DB_PATH}")
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
