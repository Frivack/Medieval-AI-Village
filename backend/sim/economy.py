# backend/sim/economy.py
# The economy's rules and numbers in one place, so tuning them with
# tools/simulate.py touches only this file (and prices.py).
#
# Flow of goods: Thomas grows wheat -> Gilbert buys it wholesale at the
# Farm -> sells it retail to Margaret at the Inn -> she cooks it into
# meals -> everyone buys meals. Thomas's farming tools wear out -> he buys
# new ones from Edmund. Everyone eats about three meals a day.
#
# Money is conserved — nothing creates or destroys copper — so prices have
# to balance these flows, or someone slowly goes broke. Per day, with F =
# one person's food spend, T = the farmer's tool spend, q = wheat units
# passing through the merchant, b = BASE_PRICES["wheat"]:
#   Edmund   earns T, eats F                    -> T = F
#   Thomas   earns 0.8*b*q, pays F + T          -> 0.8*b*q = 2F
#   Gilbert  earns 1.2*b*q - 0.8*b*q, eats F    -> 0.4*b*q = F
#   Margaret earns 3F, pays 1.2*b*q             -> (same condition)
# So: F = T = 0.4 * b * q. With q ~= 6.6 (she cooks ~13 meals/day at two
# per wheat) and 3 meals at 12c (F = 36-40c): b = 15, and a 300c tool must
# last ~8 days. The tool only wears when wheat is actually produced (a full
# store stops production), i.e. ~6.6 times a day, so 2 wear per batch.
# Tuning history (tools/simulate.py): b = 10 left Thomas at -34c/day and
# Margaret at +38c/day over 14 days; b = 15 with 1 wear per batch made a
# tool last ~15 days and Edmund sold none in 21 days (-38c/day).
#
# All functions are pure: they take and return plain dicts, the tick
# engine stores the results back on the agent.
from backend.sim.prices import BASE_PRICES

FARMER, BLACKSMITH, MERCHANT, INNKEEPER = "Farmer", "Blacksmith", "Merchant", "Innkeeper"

# --- hunger -------------------------------------------------------------
HUNGER_MAX = 100.0
HUNGER_PER_HOUR_AWAKE = 8.0
HUNGER_PER_HOUR_ASLEEP = 3.0
EAT_AT = 50.0          # eat a carried meal once hunger reaches this
MEAL_RELIEF = 50.0     # one food takes this much hunger away
FOOD_TO_CARRY = 3      # meals everyone tops up to: dinner, breakfast, lunch

# --- tools -------------------------------------------------------------
TOOL_FULL = 100
# Wear per batch actually produced (not per hour at work: a full store
# stops production and wear). Jobs listed here can't produce without a tool.
TOOL_WEAR_PER_WORK_HOUR = {FARMER: 2}
SPARE_TOOL_AT = 25     # below this, buy a spare if one is on offer nearby

# --- production -----------------------------------------------------------
# One batch per in-game hour of WORK: inputs consumed -> output produced.
RECIPES = {
    FARMER:     {"output": ("wheat", 1), "inputs": {}},
    BLACKSMITH: {"output": ("farming_tools", 1), "inputs": {}},
    INNKEEPER:  {"output": ("food", 2), "inputs": {"wheat": 1}},
}
# Producers stop once their stock reaches this — a storage limit, and what
# keeps unsold goods from piling up forever.
STOCK_CAP = {"wheat": 20, "farming_tools": 3, "food": 16}

# --- trade -------------------------------------------------------------
# Producers sell only at their own workplace; the merchant sells anywhere.
WHOLESALE = 0.8                                     # merchant buying stock from a producer
RETAIL = 1.2                                        # merchant selling
MERCHANT_STOCK = {"wheat": 10, "farming_tools": 1}  # what Gilbert keeps on hand to resell
INNKEEPER_INPUTS = {"wheat": 8}                     # Margaret's wheat buffer for cooking


def needs_of(job: str, needs) -> dict:
    """Needs with defaults filled in (rows from before 1b hold NULL)."""
    full = {"hunger": 0.0}
    if job in TOOL_WEAR_PER_WORK_HOUR:
        full["tool"] = TOOL_FULL
    full.update(needs or {})
    return full


def grow_hunger(needs: dict, asleep: bool, minutes: int) -> dict:
    rate = HUNGER_PER_HOUR_ASLEEP if asleep else HUNGER_PER_HOUR_AWAKE
    return {**needs, "hunger": round(min(HUNGER_MAX, needs["hunger"] + rate * minutes / 60), 3)}


def should_eat(needs: dict, inventory: dict) -> bool:
    return needs["hunger"] >= EAT_AT and inventory.get("food", 0) > 0


def eat(needs: dict, inventory: dict) -> tuple[dict, dict]:
    inventory = add_item(inventory, "food", -1)
    return {**needs, "hunger": max(0.0, needs["hunger"] - MEAL_RELIEF)}, inventory


def wants(job: str, inventory: dict, needs: dict) -> dict:
    """What this agent would buy right now, most important first."""
    want = {}
    if job != INNKEEPER:                       # she eats her own cooking
        want["food"] = FOOD_TO_CARRY - inventory.get("food", 0)
    if job == INNKEEPER:
        for item, target in INNKEEPER_INPUTS.items():
            want[item] = target - inventory.get(item, 0)
    if job in TOOL_WEAR_PER_WORK_HOUR and needs["tool"] <= SPARE_TOOL_AT:
        want["farming_tools"] = 1 - inventory.get("farming_tools", 0)
    if job == MERCHANT:
        for item, target in MERCHANT_STOCK.items():
            want[item] = target - inventory.get(item, 0)
    return {item: n for item, n in want.items() if n > 0}


def urgent(job: str, inventory: dict, needs: dict):
    """A need worth leaving the schedule for: the item to go and buy, or None."""
    if needs["hunger"] >= EAT_AT and inventory.get("food", 0) == 0:
        return "food"
    if (job in TOOL_WEAR_PER_WORK_HOUR and needs["tool"] <= 0
            and inventory.get("farming_tools", 0) == 0):
        return "farming_tools"
    return None


def for_sale(job: str, workplace: str, location: str, inventory: dict) -> dict:
    """What this agent will sell right now at `location`."""
    if job != MERCHANT and location != workplace:
        return {}
    never = set(RECIPES.get(job, {}).get("inputs", {}))     # cooking wheat isn't for sale
    if job in TOOL_WEAR_PER_WORK_HOUR:
        never.add("farming_tools")                           # nor the farmer's spare tool
    keep = {"food": FOOD_TO_CARRY}
    offer = {}
    for item, n in inventory.items():
        if item in never:
            continue
        spare = n - keep.get(item, 0)
        if spare > 0:
            offer[item] = spare
    return offer


def unit_price(item: str, buyer_job: str, seller_job: str) -> int:
    if seller_job == MERCHANT:
        factor = RETAIL
    elif buyer_job == MERCHANT and item in MERCHANT_STOCK:   # buying stock, not his own dinner
        factor = WHOLESALE
    else:
        factor = 1.0
    return max(1, round(BASE_PRICES[item] * factor))


def produce(job: str, inventory: dict, needs: dict) -> tuple[dict, dict, str | None]:
    """One hour of WORK. Returns (inventory, needs, event) where event says
    what happened: "produced 2 food", "no tool", "out of wheat", ..."""
    recipe = RECIPES.get(job)
    if recipe is None:
        return inventory, needs, None
    item, amount = recipe["output"]
    if inventory.get(item, 0) >= STOCK_CAP.get(item, float("inf")):
        return inventory, needs, f"{item} store full"

    wear = TOOL_WEAR_PER_WORK_HOUR.get(job)
    if wear and needs["tool"] <= 0:
        if inventory.get("farming_tools", 0) == 0:
            return inventory, needs, "no tool"
        inventory = add_item(inventory, "farming_tools", -1)     # bought a spare since: use it
        needs = {**needs, "tool": TOOL_FULL}

    missing = [i for i, n in recipe["inputs"].items() if inventory.get(i, 0) < n]
    if missing:
        return inventory, needs, f"out of {missing[0]}"
    for i, n in recipe["inputs"].items():
        inventory = add_item(inventory, i, -n)
    inventory = add_item(inventory, item, amount)
    event = f"produced {amount} {item}"

    if wear:
        needs = {**needs, "tool": max(0, needs["tool"] - wear)}
        if needs["tool"] == 0:
            if inventory.get("farming_tools", 0) > 0:
                inventory = add_item(inventory, "farming_tools", -1)
                needs = {**needs, "tool": TOOL_FULL}
                event += "; the tool wore out, took the spare"
            else:
                event += "; the tool broke"
    return inventory, needs, event


def add_item(inventory: dict, item: str, n: int) -> dict:
    out = dict(inventory)
    out[item] = out.get(item, 0) + n
    if out[item] <= 0:
        del out[item]
    return out
