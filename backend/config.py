# backend/config.py
# Central place for environment-dependent settings.
# Swap LLM endpoints by changing env vars, not code (see CLAUDE.md §3):
#   - LM Studio (local dev):       http://localhost:1234/v1
#   - Secondary machine (1080 Ti): http://<its-LAN-IP>:8000/v1 (IP in CLAUDE.local.md)
#   - Groq (deployment):           https://api.groq.com/openai/v1
import os

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

# Time: 1 tick = 5 in-game minutes.
# (1 tick = 1 hour made travel absurd: crossing the village at
# 1 tile/tick took two in-game days. At 5 min/tick it's ~4 hours.)
MINUTES_PER_TICK = 5
TICKS_PER_HOUR = 60 // MINUTES_PER_TICK   # 12
TICKS_PER_DAY = TICKS_PER_HOUR * 24       # 288
