# backend/sim/prices.py
# Base prices in copper (1 gold = 200 copper, see backend/utils/currency.py).
# Wheat, food and farming_tools are tuned so the closed economy balances
# (derivation in backend/sim/economy.py; checked with tools/simulate.py):
# 3 meals a day (36c) cost about what a day's share of a farming tool does
# (300c lasting ~8 working days), and wheat at 15c lets the farmer, the
# merchant and the innkeeper each cover that from their part of the chain.
# The sword is deliberately far cheaper than historical reality (months of
# wages) so that trading it is actually possible in the simulation.

BASE_PRICES = {
    "wheat": 15,       # was 10: at 10 the farmer went broke (-34c/day, 14-day sim)
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
