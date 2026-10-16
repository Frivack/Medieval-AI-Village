# backend/config.py
# Central place for environment-dependent settings.
# Swap LLM endpoints by changing env vars, not code (see CLAUDE.md §3):
#   - LM Studio (local dev):       http://localhost:1234/v1
#   - Secondary machine (1080 Ti): http://<its-LAN-IP>:8000/v1 (IP in CLAUDE.local.md)
#   - Groq (deployment):           https://api.groq.com/openai/v1
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent  # backend/ -> repo root

# Local secrets and settings (ANTHROPIC_API_KEY, ...) from the gitignored
# repo-root .env. Real environment variables win (override=False), so on the
# server the systemd EnvironmentFile decides.
load_dotenv(BASE_DIR / ".env", override=False)

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

# Conversations: who writes the lines and the plans (backend/llm/providers.py).
# "template" needs no LLM and costs nothing — the default, so a manual
# "+1 day" in dev can't run up a bill. "claude" uses the Claude API
# (ANTHROPIC_API_KEY); any failed call falls back to the template.
CONVERSATION_LLM = os.getenv("CONVERSATION_LLM", "template").lower()
# VILLAGE_-prefixed on purpose: Claude Code exports its own CLAUDE_EFFORT
# (e.g. "xhigh") into every shell it starts, and an unprefixed name picked
# that up — every call then failed with a 400.
CLAUDE_MODEL = os.getenv("VILLAGE_CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_EFFORT = os.getenv("VILLAGE_CLAUDE_EFFORT", "low")
CLAUDE_TIMEOUT_SECONDS = float(os.getenv("VILLAGE_CLAUDE_TIMEOUT_SECONDS", "30"))
# Safety net besides the Console spend limit: after this many calls in a
# (UTC) day, conversations fall back to templates until tomorrow. A
# simulated day needs ~70 calls; the counter resets when the server restarts.
LLM_DAILY_CALL_LIMIT = int(os.getenv("LLM_DAILY_CALL_LIMIT", "500"))

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
# A brand-new world starts on Day 1 at the server's current local time of
# day instead of 00:00, so with real-time ticks the village sleeps when its
# visitors do. Only read when the world is created (agents loaded into an
# empty DB); an existing world keeps its clock. The deploy box runs on
# Asia/Seoul time.
START_AT_LOCAL_TIME = os.getenv("VILLAGE_START_AT_LOCAL_TIME", "0").lower() in ("1", "true", "on")
