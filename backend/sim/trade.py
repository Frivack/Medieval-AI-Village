# backend/sim/trade.py
# Turning an agreed offer into goods and copper changing hands.
# Conversations make and accept offers (backend/sim/conversation.py); this
# module finds a sensible offer, checks one, and settles it.
from backend.memory.short_term import remember
from backend.sim import economy
from backend.sim.actions import ActionType
from backend.utils.currency import to_string

# A deal's price may differ from the economy's price by at most this much,
# so a hallucinating model can't wreck the economy (same idea as TRADE v2).
PRICE_CLAMP = (0.7, 1.3)


def best_offer(buyer, seller, buyer_needs: dict, place: str):
    """The most important thing on the buyer's wish list that `seller`
    sells at `place`, as many as wanted / on offer / affordable:
    {"kind": "buy", "item", "quantity", "price"} — or None."""
    stock = economy.for_sale(seller.job, seller.workplace, place, seller.inventory or {})
    for item, wanted in economy.wants(buyer.job, buyer.inventory or {}, buyer_needs).items():
        if not stock.get(item):
            continue
        unit = economy.unit_price(item, buyer.job, seller.job)
        quantity = min(wanted, stock[item], buyer.wealth // unit)
        if quantity >= 1:
            return {"kind": "buy", "item": item, "quantity": quantity, "price": unit * quantity}
    return None


def check(buyer, seller, item: str, quantity: int, price: int, place: str):
    """Why this deal can't happen, or None if it can. `price` must already
    be clamped (see clamp_price)."""
    if item not in economy.BASE_PRICES:
        return f"nobody trades '{item}'"
    if quantity < 1:
        return "nothing to trade"
    if economy.for_sale(seller.job, seller.workplace, place, seller.inventory or {}).get(item, 0) < quantity:
        return f"{seller.name} can't spare {quantity} {item}"
    if buyer.wealth < price:
        return f"{buyer.name} can't afford {to_string(price)}"
    return None


def clamp_price(item: str, quantity: int, price, buyer, seller) -> int:
    """Keep a proposed total within PRICE_CLAMP of the economy's price."""
    fair = economy.unit_price(item, buyer.job, seller.job) * quantity
    try:
        price = int(price)
    except (TypeError, ValueError):
        return fair
    low, high = (max(1, round(fair * f)) for f in PRICE_CLAMP)
    return min(max(price, low), high)


def settle(buyer, seller, item: str, quantity: int, total: int, tick: int) -> list[dict]:
    """Move goods and copper both ways (callers have run check()).
    Returns one history event per side."""
    buyer.inventory = economy.add_item(buyer.inventory or {}, item, quantity)
    seller.inventory = economy.add_item(seller.inventory or {}, item, -quantity)
    buyer.wealth -= total
    seller.wealth += total
    # Buying the daily meals is routine; a deal over wheat or tools is news.
    importance = 1 if item == "food" else 3
    remember(buyer, tick, f"I bought {quantity} {item} from {seller.name} for {to_string(total)}.",
             importance)
    remember(seller, tick, f"I sold {quantity} {item} to {buyer.name} for {to_string(total)}.",
             importance)
    detail = f"{buyer.name} bought {quantity} {item} from {seller.name} for {to_string(total)}"
    return [
        {"agent_id": buyer.id, "action": ActionType.TRADE.value, "copper_change": -total,
         "item": item, "quantity": quantity, "seller": seller.name, "buyer": buyer.name,
         "detail": detail},
        {"agent_id": seller.id, "action": ActionType.TRADE.value, "copper_change": total,
         "item": item, "quantity": quantity, "seller": seller.name, "buyer": buyer.name,
         "detail": detail},
    ]
