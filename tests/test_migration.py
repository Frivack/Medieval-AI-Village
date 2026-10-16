# add_missing_columns() must upgrade an older village.db in place.
from sqlalchemy import create_engine, inspect, text

from backend.database import Base, add_missing_columns


def test_adds_a_new_model_column_to_an_old_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    # An agent_states table as it looked before the `needs` column existed.
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE agent_states (id VARCHAR PRIMARY KEY, name VARCHAR)'))
        conn.execute(text("INSERT INTO agent_states (id, name) VALUES ('a1', 'Thomas')"))
    Base.metadata.create_all(engine)          # makes the other tables, leaves this one alone

    added = add_missing_columns(engine, Base.metadata)

    assert "agent_states.needs" in added
    cols = {c["name"] for c in inspect(engine).get_columns("agent_states")}
    assert {"needs", "daily_plan", "inventory"} <= cols
    with engine.connect() as conn:            # the old row survived, new column is NULL
        assert conn.execute(text("SELECT name, needs FROM agent_states")).one() == ("Thomas", None)


def test_is_a_no_op_on_an_up_to_date_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    Base.metadata.create_all(engine)
    assert add_missing_columns(engine, Base.metadata) == []
