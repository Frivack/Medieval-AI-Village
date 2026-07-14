# backend/sim/prices.py
# Base prices in copper (1 gold = 200 copper, see backend/utils/currency.py).
# Anchor: one day of a farmer's WORK output (12 wheat) ~= 120 copper, so an
# evening meal + ale at the inn (~18c) is ~15% of a day's income — roughly
# in line with how large a share of income food took in a medieval economy.
# The sword is deliberately far cheaper than historical reality (months of
# wages) so that trading it is actually possible in the simulation.

BASE_PRICES = {
    "wheat": 10,
    "vegetables": 8,
    "ale": 6,
    "food": 12,        # a cooked meal at the inn
    "farming_tools": 300,
    "sword": 1500,
}


def price_of(item: str, quantity: int = 1) -> int | None:
    """Total price in copper, or None for unknown items."""
    unit = BASE_PRICES.get(item)
    return None if unit is None else unit * quantity
