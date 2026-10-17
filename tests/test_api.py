# The villager detail route, run against the throwaway test database:
# FastAPI's dependency override swaps get_db for the test session, so the
# real data/village.db is never touched (and the lifespan never runs).
import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.database import Conversation, Relationship, SimState, TickHistory, get_db
from backend.main import app
from backend.sim import schedule
from backend.sim.clock import tick_at
from tests.helpers import EVENING, villager


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_villager_detail(db, client):
    thomas = villager(db, "Thomas", "Farmer", "Farm")
    villager(db, "Edmund", "Blacksmith", "Smithy")
    villager(db, "Gilbert", "Merchant", "Market")
    db.add(SimState(id=1, tick=EVENING))
    # An appointment the AI added, with its reason.
    thomas.daily_plan = schedule.insert(thomas.daily_plan, {
        "start": tick_at(3, 7), "end": tick_at(3, 8), "do": "VISIT", "at": "Smithy",
        "with": "Edmund", "why": "buy new farming tools", "source": schedule.AI, "day": 3})
    db.add_all([Relationship(agent_id="thomas", other_id="edmund", affinity=6, last_talk_tick=EVENING),
                Relationship(agent_id="edmund", other_id="thomas", affinity=-6)])
    thomas.short_term_memory = [{"tick": 100, "text": "Old news.", "importance": 1},
                                {"tick": 200, "text": "Edmund will sell me tools.",
                                 "importance": 3, "told": ["Gilbert"]}]
    db.commit()

    data = client.get("/villagers/thomas").json()

    visit = next(b for b in data["schedule"] if b["do"] == "VISIT")
    assert visit["ai"] and visit["why"] == "buy new farming tools" and visit["with"] == "Edmund"
    assert visit["from"] == "Day 3 07:00" and not visit["current"]
    assert next(b for b in data["schedule"] if b["current"])["do"] == "SOCIAL"   # 19:00 at the Inn
    assert all(not b["ai"] for b in data["schedule"] if b is not visit)
    edmund, gilbert = data["relationships"]                                       # sorted by name
    assert (edmund["affinity"], edmund["level"]) == (6, "like")
    assert (edmund["their_affinity"], edmund["their_level"]) == (-6, "wary")    # it isn't mutual
    assert edmund["last_talk"] == "Day 2 19:00"
    assert (gilbert["affinity"], gilbert["level"], gilbert["last_talk"]) == (0, "neutral", None)
    assert [m["text"] for m in data["memories"]] == ["Edmund will sell me tools.", "Old news."]
    assert data["memories"][0]["told"] == ["Gilbert"]


def test_unknown_villager_is_404(client):
    assert client.get("/villagers/nobody").status_code == 404


def test_list_routes_cap_the_limit(db, client, monkeypatch):
    monkeypatch.setattr(main, "MAX_LIST", 3)
    for i in range(5):
        db.add(Conversation(a_id="a", b_id="b", place="Inn", reason="chat", started_tick=i,
                            status="ended", next_speaker_id="a", lines=[], deals=[]))
        db.add(TickHistory(tick=i, agent_id="a", action="TALK", dialogue="Hello."))
    db.commit()
    assert len(client.get("/conversations?limit=100000000").json()) == 3
    assert len(client.get("/history?limit=100000000&notable=true").json()) == 3
    assert len(client.get("/conversations?limit=0").json()) == 1      # at least one

