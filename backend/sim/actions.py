# backend/sim/actions.py
# What an agent did in a tick, as recorded in TickHistory.action.
# (What each job produces now lives in backend/sim/economy.py RECIPES.)
from enum import Enum


class ActionType(str, Enum):
    MOVE = "MOVE"
    WORK = "WORK"
    TALK = "TALK"
    TRADE = "TRADE"
    REST = "REST"
    EAT = "EAT"
    OBSERVE = "OBSERVE"
