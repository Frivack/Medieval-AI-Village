# Medieval AI Village — Project Context & Handoff

> Purpose of this file: give an AI coding agent (Claude Code) enough context to
> continue this project without re-explaining it. Written to sit at the repo root
> as `CLAUDE.md` so it loads automatically at session start.
>
> Repo: https://github.com/Frivack/Medieval-AI-Village · License: MIT

---

## 1. What this project is

A **multi-agent LLM simulation** of a medieval village, inspired by Stanford's
*Generative Agents* paper. Each villager is an LLM-driven character that acts,
works, talks, and trades on its own. The end goal is a **web-viewable** village
that runs the simulation and visualizes it in the browser. It's a personal
project intended for **public release and as a portfolio piece**.

---

## 2. Core design principle: English-first (do not break this)

Everything the model sees — **agent names, prompts, world/state descriptions,
and JSON config** — is written in **English**. This is deliberate:

- The small local models used in development reason noticeably better in English.
- Non-English input gets internally translated by the model anyway, so
  English-first is simply the more reliable default.

**Keep all new agent-facing content, prompts, and identifiers in English.**

---

## 3. Current state (what works today)

*(Updated 2026-07-14 to match the actual source — the previous version of this
section described work that was never committed.)*

### Backend
- **FastAPI** server (`backend/main.py`), startup via lifespan handler.
- **SQLite via SQLAlchemy** (`backend/database.py`) — `AgentState`,
  `TickHistory`, `SimState` (world tick counter).
- `data/village.db` is runtime state: gitignored, regenerated from
  `data/agents.json` on startup. Delete it to reset the world.
- `.claude/launch.json` holds the dev-server config so Claude Code's
  browser preview can start uvicorn (local port 8000).

### Agents
Four agents, defined together in **`data/agents.json`** (single file, one
entry per agent, includes `workplace`):

| Name     | Role       | Workplace |
|----------|------------|-----------|
| Thomas   | Farmer     | Farm      |
| Edmund   | Blacksmith | Smithy    |
| Gilbert  | Merchant   | Market    |
| Margaret | Innkeeper  | Inn       |

### World (roadmap items 1–4 — implemented)
- **Tile map:** 100×50 grid, generated deterministically in
  `backend/world/map.py` (grass/water/forest/field, river + bridge, four
  buildings with walls/floor/door). `GET /map` serializes it.
- **A\* pathfinding:** `backend/world/pathfinding.py`, 4-directional,
  agents move **1 tile per tick**; remaining path is stored on the agent row.
- **Structured actions:** `MOVE`, `WORK`, `TALK`, `REST`, `OBSERVE` executed
  in `backend/sim/tick_engine.py`. `TRADE` is declared but not implemented
  yet (falls back to OBSERVE).
- **Time:** **1 tick = 5 in-game minutes** (12 ticks/hour, 288/day);
  day/hour/minute derived from `SimState.tick`. Chosen because 1 tick =
  1 hour made 1-tile-per-tick travel absurdly slow (two days to cross
  the village). WORK yields its product once per in-game hour (on the
  minute-0 tick); sleeping agents skip re-decisions until 06:00 to save
  LLM calls. `POST /tick?count=N` advances up to one day per call;
  `GET /time`, `GET /history` for inspection.

### LLM integration
- `backend/llm/client.py` — OpenAI-compatible `/chat/completions` via httpx.
  Endpoint/model come from env vars (`LLM_BASE_URL`, `LLM_MODEL`); defaults
  to LM Studio at `http://localhost:1234/v1` (see `backend/config.py`).
- `backend/sim/decider.py` asks the LLM for a structured JSON action per
  agent per tick. **If the LLM server is unreachable it falls back to a
  rule-based daily routine** (work by day, inn in the evening, sleep at
  night), so the simulation always runs.

### Currency
- **Copper-based economy**, with **1 gold = 200 copper** (`backend/utils/currency.py`).
  This rate was chosen to balance historical plausibility against
  computational simplicity (the ratio was researched before it was committed).

### Memory / retrieval
- **ChromaDB is NOT integrated yet.** It remains the intended vector store
  for agent memory retrieval (Generative Agents approach); `short_term_memory`
  exists as a JSON column on `AgentState` but nothing writes to it yet.

---

## 4. Architecture conventions (maintain these)

- **Clean architecture from the start** is preferred over quick prototypes.
- Clear separation of concerns: **JSON config** (agent definitions) vs.
  **SQLite** (runtime state).
- Proper **module-level imports** and well-structured code.

---

## 5. Development environment (two-machine setup)

### Main PC — primary development
- **Windows**, using **PyCharm** + **Anaconda**.
- Where most of the coding happens.

### Secondary machine — heavy compute
- **Ubuntu 24.04 LTS**, **GTX 1080 Ti (11 GB VRAM)**.
- **Kept powered off when not in use** to save on electricity — power it on
  before running compute jobs on it.
- **Local LLM server:** `llama.cpp` **built from source with CUDA**
  (`cmake -B build -DGGML_CUDA=ON`).
  - Serves on **port 8000**, OpenAI-compatible API.
  - Throughput **~40 tokens/sec**.
  - Models present: `llama3.1-8b`, `Qwen3.5-9B`.
  - Python venv at `~/llm-env`.
  - System prompt file: `~/llm-system-prompt.txt` (injected via the Python API calls).
  - Shell aliases:
    - `llmenv`  — activate the Python venv.
    - `llmstart` — start the llama.cpp server.

### Networking / SSH
- Main → secondary over the **local network via SSH**, using **MobaXterm** on Windows.
- Secondary connects through a **USB wireless LAN adapter** with a fixed IP
  (DHCP reservation by MAC on the home router). **The adapter's MAC and the
  fixed IP live in `CLAUDE.local.md`** (gitignored — no network details in
  committed files).
- ⚠️ The fixed IP is tied to that adapter's MAC. **Swapping the USB wireless
  adapter changes the MAC and breaks the reservation / SSH.** Don't swap it
  without re-doing the router reservation.

### Deployment — LIVE (since 2026-07-14)
- Deployed on an **Oracle Cloud instance** (Ubuntu 22.04 x86_64, 1 GB RAM),
  running via `nohup` (**not boot-persistent** — it dies on reboot;
  registering a systemd service was deliberately deferred by the developer
  on 2026-07-15, ask before setting it up).
- No LLM on that box → the simulation runs on the rule-based fallback.
  For real LLM behavior set `LLM_BASE_URL` (e.g. Groq) in the environment.
- **Addresses, SSH access, ports and the restart procedure live in
  `CLAUDE.local.md`** (gitignored — this repo is public, so no
  infrastructure details belong in committed files).

---

## 6. Roadmap — next planned work (in order)

Backend world + movement first; frontend after.

1. ~~**Tile-based open-world map**~~ ✅ done — 100×50 grid, walkable/resource
   tiles, building interiors (`backend/world/`).
2. ~~**A\* pathfinding**~~ ✅ done — agents move 1 tile per tick.
3. **Structured action types** — mostly done: `MOVE`, `WORK`, `TALK`, `REST`,
   `OBSERVE` work; **`TRADE` still needs a real implementation** (price
   negotiation, inventory/copper exchange between agents).
4. ~~**Time system**~~ ✅ done — 1 tick = 5 in-game minutes (`SimState.tick`).
5. **Agent memory** — write observations/conversations into
   `short_term_memory`, then ChromaDB retrieval (Generative Agents style).
6. **Frontend** (queued after the above)
   - **React + Vite**, web visualization of the village (`GET /map` +
     `GET /villagers` already return everything a renderer needs).

---

## 7. Known issues / gotchas

- Secondary machine's **CMOS battery is aging** — may need replacement (can cause
  clock/BIOS reset issues).
- **Don't swap the USB wireless adapter** without updating the router's DHCP
  reservation (see §5).
- **QLoRA is the only viable fine-tuning approach** on the 11 GB card, if/when
  fine-tuning is attempted.
- **Pre-built `llama.cpp` binaries and pip packages** hit GPU-architecture
  compatibility issues — **building from source with CUDA is the fix.**
- **`pkill -f uvicorn` over SSH kills your own session**: the remote
  `bash -c` command line contains the pattern too. Kill by PID
  (`pgrep -af venv/bin/uvicorn` first), or bracket-escape the pattern.
- **Driving `ssh` from Windows PowerShell mangles quotes**: inner double
  quotes in the remote command get stripped by PowerShell 5.1 argument
  parsing. Prefer remote commands that need no nested quoting.
- The deployment box has a **pending kernel upgrade** — it will want a
  reboot at some point; remember the app doesn't auto-start (see §5 and
  `CLAUDE.local.md`).

---

## 8. How the developer likes to work (collaboration style)

Please follow these when continuing the project:

- The developer **types code manually rather than pasting** — provide code in
  clear, copyable steps; don't dump one giant block at once.
- **Explain concepts as you go.** They actively want to understand the *why*
  (e.g., REST vs. FastAPI distinctions, why imports go where they do).
- **Incremental, step-by-step progression** with explanations — not big upfront
  rewrites or a large review dumped at the end.
- **Collaborative bug-catching during implementation**, rather than one big
  review pass afterward.
- **Research design decisions before committing** (as was done for the currency
  rate).

---

## 9. First steps for the AI agent

This document can drift from the code. Before making changes, get current ground
truth from the actual repo:

1. Read the repo structure and existing modules.
2. Check the **FastAPI entry point and route definitions**.
3. Check the **SQLAlchemy models / DB schema**.
4. Check the **agent JSON config schema** in `data/agents.json` (one file,
   four agents).
5. Check the **tick engine** implementation and how it calls the LLM.
6. Confirm current **ChromaDB** integration status.
7. Confirm how the **LLM endpoint is configured** (local LM Studio vs. the
   secondary machine on `:8000` vs. Groq) so you point at the right base URL.
