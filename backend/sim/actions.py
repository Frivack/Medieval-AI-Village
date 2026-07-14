# backend/sim/actions.py
from enum import Enum


class ActionType(str, Enum):
    MOVE = "MOVE"
    WORK = "WORK"
    TALK = "TALK"
    TRADE = "TRADE"
    REST = "REST"
    OBSERVE = "OBSERVE"


# What each job produces when it WORKs.
JOB_PRODUCT = {
    "Farmer": "wheat",
    "Blacksmith": "farming_tools",
    "Merchant": None,       # merchants trade, they don't produce
    "Innkeeper": "food",
}
