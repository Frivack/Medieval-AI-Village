# Unit tests for backend/sim/economy.py — the rules, not the tuned numbers:
# assertions are written against the module's constants where possible.
from backend.sim import economy as e
from backend.sim.prices import BASE_PRICES


def test_needs_defaults_cover_old_rows():
    assert e.needs_of("Farmer", None) == {"hunger": 0.0, "tool": e.TOOL_FULL}
    assert e.needs_of("Blacksmith", {}) == {"hunger": 0.0}
    assert e.needs_of("Farmer", {"hunger": 30})["hunger"] == 30


def test_hunger_grows_slower_asleep_and_caps():
    n = {"hunger": 0.0}
    assert e.grow_hunger(n, asleep=False, minutes=60)["hunger"] == e.HUNGER_PER_HOUR_AWAKE
    assert e.grow_hunger(n, asleep=True, minutes=60)["hunger"] == e.HUNGER_PER_HOUR_ASLEEP
    assert e.grow_hunger({"hunger": 99.0}, False, 600)["hunger"] == e.HUNGER_MAX


def test_eating_needs_food_and_hunger():
    hungry, full = {"hunger": e.EAT_AT}, {"hunger": e.EAT_AT - 1}
    assert e.should_eat(hungry, {"food": 1})
    assert not e.should_eat(hungry, {})
    assert not e.should_eat(full, {"food": 1})
    needs, inv = e.eat(hungry, {"food": 1, "wheat": 2})
    assert needs["hunger"] == e.EAT_AT - e.MEAL_RELIEF and inv == {"wheat": 2}


def test_wants_by_job():
    assert e.wants("Farmer", {}, e.needs_of("Farmer", None)) == {"food": e.FOOD_TO_CARRY}
    worn = {"hunger": 0.0, "tool": e.SPARE_TOOL_AT}
    assert e.wants("Farmer", {"food": 3}, worn) == {"farming_tools": 1}
    assert e.wants("Innkeeper", {"food": 0, "wheat": 2}, {"hunger": 0.0}) == {
        "wheat": e.INNKEEPER_INPUTS["wheat"] - 2}
    assert e.wants("Merchant", {"food": 3, "wheat": 4, "farming_tools": 1}, {"hunger": 0.0}) == {
        "wheat": e.MERCHANT_STOCK["wheat"] - 4}


def test_urgent_needs():
    assert e.urgent("Smith", {}, {"hunger": e.EAT_AT}) == "food"
    assert e.urgent("Smith", {"food": 1}, {"hunger": e.EAT_AT}) is None   # just eat it
    assert e.urgent("Farmer", {"food": 1}, {"hunger": 0.0, "tool": 0}) == "farming_tools"


def test_producers_sell_only_at_their_workplace_merchant_anywhere():
    inv = {"wheat": 12, "food": 5}
    assert e.for_sale("Farmer", "Farm", "Inn", inv) == {}
    assert e.for_sale("Farmer", "Farm", "Farm", inv) == {"wheat": 12, "food": 5 - e.FOOD_TO_CARRY}
    assert e.for_sale("Merchant", "Market", "Inn", inv) == {"wheat": 12, "food": 5 - e.FOOD_TO_CARRY}


def test_inputs_and_the_farmers_spare_tool_are_never_sold():
    assert "wheat" not in e.for_sale("Innkeeper", "Inn", "Inn", {"wheat": 9, "food": 10})
    assert "farming_tools" not in e.for_sale("Farmer", "Farm", "Farm", {"farming_tools": 2})


def test_prices_wholesale_retail_and_direct():
    base = BASE_PRICES["wheat"]
    assert e.unit_price("wheat", "Merchant", "Farmer") == round(base * e.WHOLESALE)
    assert e.unit_price("wheat", "Innkeeper", "Merchant") == round(base * e.RETAIL)
    assert e.unit_price("food", "Farmer", "Innkeeper") == BASE_PRICES["food"]
    # The merchant buying his own dinner pays the normal price, not wholesale.
    assert e.unit_price("food", "Merchant", "Innkeeper") == BASE_PRICES["food"]


def test_cooking_consumes_wheat_and_stops_without_it():
    inv, _, event = e.produce("Innkeeper", {"wheat": 1}, {"hunger": 0.0})
    assert inv == {"food": e.RECIPES["Innkeeper"]["output"][1]} and event.startswith("produced")
    inv, _, event = e.produce("Innkeeper", {"food": 1}, {"hunger": 0.0})
    assert inv == {"food": 1} and event == "out of wheat"


def test_stock_cap_stops_production():
    full = {"farming_tools": e.STOCK_CAP["farming_tools"]}
    inv, _, event = e.produce("Blacksmith", full, {"hunger": 0.0})
    assert inv == full and event == "farming_tools store full"


def test_farming_wears_the_tool_until_it_breaks():
    wear = e.TOOL_WEAR_PER_WORK_HOUR["Farmer"]
    _, needs, event = e.produce("Farmer", {}, {"hunger": 0.0, "tool": wear})
    assert needs["tool"] == 0 and event.endswith("the tool broke")
    inv, _, event = e.produce("Farmer", {}, needs)
    assert event == "no tool" and inv == {}
    # A spare bought afterwards is taken into use on the next hour of work.
    inv, needs, event = e.produce("Farmer", {"farming_tools": 1}, {"hunger": 0.0, "tool": 0})
    assert "farming_tools" not in inv and inv["wheat"] == 1 and needs["tool"] == e.TOOL_FULL - wear
