# backend/config.py
# Central place for environment-dependent settings.
# Swap LLM endpoints by changing env vars, not code (see CLAUDE.md §3):
#   - LM Studio (local dev):       http://localhost:1234/v1
#   - Secondary machine (1080 Ti): http://<its-LAN-IP>:8000/v1 (IP in CLAUDE.local.md)
#   - Groq (deployment):           https://api.groq.com/openai/v1
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # backend/ -> repo root

# The world's runtime state. VILLAGE_DB_PATH points tests and the offline
# simulator (tools/simulate.py) at a throwaway file instead of the dev world.
DB_PATH = Path(os.getenv("VILLAGE_DB_PATH") or BASE_DIR / "data" / "village.db")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1-8b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")  # local servers ignore it

# Short connect timeout so the simulation falls back to rule-based
# decisions quickly when no LLM server is running.
LLM_CONNECT_TIMEOUT = float(os.getenv("LLM_CONNECT_TIMEOUT", "2.0"))
LLM_READ_TIMEOUT = float(os.getenv("LLM_READ_TIMEOUT", "30.0"))

# World
MAP_WIDTH = 100
MAP_HEIGHT = 50

# Memory
# VECTOR_MEMORY=0 disables ChromaDB even if installed; when chromadb
# isn't installed at all it degrades to short-term memory automatically.
VECTOR_MEMORY = os.getenv("VECTOR_MEMORY", "1").lower() not in ("0", "false", "off")
CHROMA_DIR = BASE_DIR / "data" / "chroma"
SHORT_TERM_MEMORY_LIMIT = 50   # newest N entries kept on the agent row
MEMORIES_IN_PROMPT = 8         # recent memories shown to the LLM

# Time: 1 tick = 1 in-game minute. With one tick per 60 real seconds
# (TICK_INTERVAL_SECONDS=60) the village runs at real-time speed.
# History: 1 h/tick made 1-tile-per-tick travel take two in-game days;
# 5 min/tick still took 4 hours from the Farm to the Inn, which broke the
# daily routine. At 1 min/tick that walk is 48 minutes.
MINUTES_PER_TICK = 1
TICKS_PER_HOUR = 60 // MINUTES_PER_TICK   # 60
TICKS_PER_DAY = TICKS_PER_HOUR * 24       # 1440

# Who advances time (see backend/sim/runner.py).
# TICK_INTERVAL_SECONDS > 0: the server ticks by itself, one tick every N
# real seconds — the public deployment. 0 (default) = no background loop;
# time only moves through POST /tick, as in local dev.
TICK_INTERVAL_SECONDS = float(os.getenv("TICK_INTERVAL_SECONDS", "0"))
# POST /tick lets any caller advance time, and every tick costs LLM calls.
# On for local dev; set MANUAL_TICK_ENABLED=0 on the public server.
MANUAL_TICK_ENABLED = os.getenv("MANUAL_TICK_ENABLED", "1").lower() not in ("0", "false", "off")
