# The Claude speaker/planner without the network: prompts render from real
# views, replies map back to engine turns, and every kind of failure ends
# in ClaudeUnavailable -> the template. A fake client stands in for the API.
import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from backend.llm import claude, prompts, providers, usage
from backend.sim import conversation as conv
from backend.sim import speech
from tests.helpers import EVENING, villager


@pytest.fixture(autouse=True)
def fresh_usage():
    usage.reset()


@pytest.fixture
def views(db):
    gilbert = villager(db, "Gilbert", "Merchant", "Market", {"food": 0})
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"food": 10})
    convo = conv.start(db, gilbert, margaret, "trade", {"item": "food"}, EVENING)
    return {"speaker": speech.speaker_view(convo, gilbert, margaret, EVENING, 0, conv.MAX_LINES),
            "wake": speech.wake_view(margaret, EVENING)}


class FakeClient:
    """messages.create() returns the queued reply (or raises it)."""

    def __init__(self, reply=None, stop_reason="end_turn"):
        self.requests, self.reply, self.stop_reason = [], reply, stop_reason
        self.messages = self
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create_beta))

    def create_beta(self, **request):
        return self.create(**request, via_beta=True)

    def create(self, **request):
        self.requests.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=json.dumps(self.reply))],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20,
                                  cache_creation_input_tokens=0, cache_read_input_tokens=900))


@pytest.fixture
def fake(monkeypatch):
    def install(reply=None, stop_reason="end_turn", model="claude-haiku-5-5"):
        client = FakeClient(reply, stop_reason)
        monkeypatch.setattr(claude, "_client", client)
        monkeypatch.setattr(claude, "CLAUDE_MODEL", model)
        return client
    return install


def test_prompts_render_from_real_views(views):
    text = prompts.speaker_prompt(views["speaker"])
    assert "You are Gilbert" in text and "you want to buy food from them" in text
    assert "Margaret sells here: food" in text and "Your turn, Gilbert." in text
    plan = prompts.plan_prompt(views["wake"])
    assert "you just woke up" in plan and "WORK at Inn" in plan and "— routine" in plan


def test_the_speaker_sees_deals_already_done(db):
    gilbert = villager(db, "Gilbert", "Merchant", "Market", {"food": 0})
    margaret = villager(db, "Margaret", "Innkeeper", "Inn", {"food": 10})
    by_id, relations = {a.id: a for a in (gilbert, margaret)}, conv.Relations(db)
    convo = conv.start(db, gilbert, margaret, "trade", {"item": "food"}, EVENING)
    now = EVENING
    while not convo.deals:                     # template lines: offer, then accept
        conv.advance(convo, by_id, now, relations)
        now += 1
    text = prompts.speaker_prompt(speech.speaker_view(convo, gilbert, margaret, now, 0,
                                                      conv.MAX_LINES - len(convo.lines)))
    deal = "Gilbert bought 3 food from Margaret for 36c"
    assert f"Already done in this conversation (goods and coin have changed hands): {deal}." in text
    assert f"[deal done: {deal}]" in text


def test_schemas_are_strict_objects():
    for schema in (prompts.TURN_SCHEMA, prompts.PLAN_SCHEMA, prompts.WAKE_SCHEMA):
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    assert set(prompts.WAKE_SCHEMA["properties"]) == {"change", "ops"}     # edits only
    assert prompts.TURN_SCHEMA["properties"]["offer"]["anyOf"][0]["properties"]["item"]["enum"] == prompts.ITEMS


def test_replies_map_back_to_engine_turns_and_plans():
    view = {"news": [{"id": "n1", "tick": 5, "text": "The bridge is out."}]}
    turn = prompts.turn_from_json({"line": "Hi!", "offer": None, "response": None,
                                   "share": "n1", "end": False}, view)
    assert turn["share"]["text"] == "The bridge is out."
    assert prompts.turn_from_json({"line": "Hi!", "share": "n9"}, view)["share"] is None

    plan = prompts.plan_from_json({"change": True, "memory": "Meet Edmund.", "importance": 2,
                                   "affinity": 1, "ops": [{"op": "cancel", "block": "b9",
                                                           "day": None, "with": None}]})
    assert plan["ops"] == [{"op": "cancel", "block": "b9"}]
    assert plan["memory"] == {"text": "Meet Edmund.", "importance": 2}
    assert prompts.plan_from_json({"change": "yes", "memory": " "})["change"] is False


def test_a_turn_request_and_its_cost(views, fake):
    client = fake({"line": "Good evening, Margaret!", "offer": None, "response": None,
                   "share": None, "end": False})
    turn = claude.claude_turn(views["speaker"])
    assert turn["line"] == "Good evening, Margaret!"
    request = client.requests[0]
    assert request["model"] == "claude-haiku-5-5" and request["thinking"] == {"type": "disabled"}
    assert "via_beta" not in request and "fallbacks" not in request   # Haiku has no fallback
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": prompts.TURN_SCHEMA}
    today = usage.snapshot()
    assert today["calls"] == 1 and today["input_tokens"] == 1000
    assert today["cost_usd"] == pytest.approx((100 + 900 * 0.1) * 0.10 / 1e6 + 20 * 0.50 / 1e6)


def test_opus_runs_with_the_server_fallback_and_its_own_cache_price(views, fake):
    client = fake({"change": False, "ops": []}, model="claude-opus-5-5")
    plan = claude.claude_plan(views["wake"])
    assert plan == {"change": False, "ops": [], "memory": None, "affinity": 0}
    request = client.requests[0]
    assert request["system"][0]["text"] == prompts.WAKE_SYSTEM
    assert request["output_config"]["format"]["schema"] == prompts.WAKE_SCHEMA
    assert "thinking" not in request                      # can't be disabled on Opus 5.5
    assert request["via_beta"] and request["fallbacks"] == "default"
    assert request["betas"] == ["server-side-fallback-2026-07-01"]
    # Opus 5.5 cache reads are $0.20/MTok (0.05x input), not 0.1x.
    assert usage.snapshot()["cost_usd"] == pytest.approx((100 * 4.0 + 900 * 0.20 + 20 * 20.0) / 1e6)


@pytest.mark.parametrize("reply, stop_reason, why", [
    ({"line": "x"}, "refusal", "declined"),
    ({"line": "x"}, "max_tokens", "max_tokens"),
    (["not", "an", "object"], "end_turn", "not a JSON object"),
    (anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid")),
     "end_turn", "APIConnectionError"),
])
def test_failures_raise_unavailable(views, fake, reply, stop_reason, why):
    fake(reply, stop_reason)
    with pytest.raises(claude.ClaudeUnavailable, match=why):
        claude.claude_turn(views["speaker"])


def test_the_daily_limit_stops_calls_before_the_network(views, fake, monkeypatch):
    client = fake({"line": "x"})
    monkeypatch.setattr(claude, "LLM_DAILY_CALL_LIMIT", 0)
    with pytest.raises(claude.ClaudeUnavailable, match="daily limit"):
        claude.claude_turn(views["speaker"])
    assert client.requests == []


def test_providers_fall_back_to_the_template(views, monkeypatch):
    assert providers.conversation_functions() == (speech.template_turn, speech.template_replan)

    def broken(view):
        raise claude.ClaudeUnavailable("down")

    monkeypatch.setattr(providers, "CONVERSATION_LLM", "claude")
    monkeypatch.setattr(claude, "claude_turn", broken)
    monkeypatch.setattr(claude, "claude_plan", broken)
    speak, plan = providers.conversation_functions()
    assert speak(views["speaker"]) == speech.template_turn(views["speaker"])
    assert plan(views["wake"]) == speech.template_replan(views["wake"])
