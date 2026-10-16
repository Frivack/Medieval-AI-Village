COPPER_PER_SILVER = 10
SILVER_PER_GOLD = 20
COPPER_PER_GOLD = COPPER_PER_SILVER * SILVER_PER_GOLD  # 200

def to_copper(gold=0, silver=0, copper=0) -> int:
    return (gold * COPPER_PER_GOLD) + (silver * COPPER_PER_SILVER) + copper

def to_display(copper: int) -> dict:
    gold = copper // COPPER_PER_GOLD
    remainder = copper % COPPER_PER_GOLD
    silver = remainder // COPPER_PER_SILVER
    copper_left = remainder % COPPER_PER_SILVER
    return {
        "gold": gold,
        "silver": silver,
        "copper": copper_left
    }

def to_string(copper: int) -> str:
    d = to_display(copper)
    parts = []
    if d["gold"] > 0:
        parts.append(f"{d['gold']}g")
    if d["silver"] > 0:
        parts.append(f"{d['silver']}s")
    if d["copper"] > 0:
        parts.append(f"{d['copper']}c")
    return " ".join(parts) if parts else "0c"

def with_copper(copper: int, quantity: int = 1) -> str:
    """An amount for text a model reads: coins plus the copper total, and
    the price per unit when it covers more than one —
    "3s 4c (34c, 17c each)". Bare coins alone got misread: "14 silver for
    eight" was retold as "35c apiece" (1 silver taken as 20 copper)."""
    coins = to_string(copper)
    extra = [] if coins == f"{copper}c" else [f"{copper}c"]
    if quantity > 1:
        extra.append(f"{copper / quantity:g}c each")
    return f"{coins} ({', '.join(extra)})" if extra else coins
