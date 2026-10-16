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
  `VILLAGE_DB_PATH` points the app at another file (tests, simulator).
- **Tests:** `python -m pytest` (pytest is in `requirements-dev.txt`;
  `pytest.ini` sets the repo root on the path). **Offline simulator:**
  `python tools/simulate.py --days 3` runs the world on a throwaway DB
  with no LLM and prints everyone's most common state per hour, Inn
  arrivals, stuck agents and the end-state economy. `--llm claude
  --model X --max-cost USD` runs it with **paid** Claude calls and stops
  at the cost cap (or when the first 5 calls all fail); `--export F`
  writes every speaker/planner call, the conversations and the usage as
  JSON — the stage 3 model comparison came from it.
- `.claude/launch.json` holds the dev-server config so Claude Code's
  browser preview can start uvicorn (local port 8000).
  `ai-village-api-live` (port 8001) previews production mode locally:
  server-driven ticks every 10 s, manual ticks off. It ticks the same
  `data/village.db`, so don't run it next to `ai-village-api`.

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
- **Actions** (`ActionType`): `MOVE`, `WORK`, `TALK`, `TRADE`, `REST`,
  `EAT`, `OBSERVE`, executed in `backend/sim/tick_engine.py`. One
  `TickHistory` row per agent per tick (TALK rows carry the line in
  `dialogue`), plus one TRADE row per side of a settled deal (`gold_change`
  column, value in copper). Settlement lives in `backend/sim/trade.py`
  (best offer, checks, 70–130% price clamp, settle).
- **Conversations** (`backend/sim/conversation.py`, stage 2, since
  2026-10-16): 1:1, **one line per tick**, turns alternate; tables
  `Conversation` (transcript, pending offer, deals, end reason) and
  `Relationship` (directed affinity −10..10, last talk tick).
  - *Start* (code, `pick()`): same building, both awake/standing/free.
    Reasons in order: trade (someone here sells what I want — this is how
    all buying happens now), appointment (a VISIT block `with` them), news
    (an unshared memory of importance ≥ 2; a memory naming the listener
    isn't news to them), chat (5%/minute per pair). News and chat only off
    work, with someone off work or hosting at their own workplace. A pair
    waits 2 in-game hours before talking again, except for an urgent need.
  - *A turn* (`speech.py`): the engine builds a speaker *view* (profile,
    needs, schedule block, partner, affinity, transcript, the partner's
    pending offer, the best thing I could buy from them, what they sell at
    what price, unshared news, price list, lines left) and calls a
    *speaker* `view -> {line, end, offer, response, share}`. Accepting the
    partner's offer settles it at once (checked + clamped); one pending
    offer at a time; max 8 lines; bedtime ends it; an unanswered offer
    lapses. Told news is marked and the listener remembers "X told me: …".
  - *After* (`end()`): each side gets a *planner* call `view -> {change,
    ops, memory, affinity}` (`apply_plan()`, shared with the wake-up
    plan): ops are validated and applied by `schedule.apply_ops`, the
    memory is stored (importance 1–3), affinity moves ≤ 2 per
    conversation, last talk is recorded. What each side made of it lands
    in `Conversation.replans` (applied / rejected ops with the reason,
    memory, affinity).
  - *Templates* (`template_turn` / `template_replan`): answer offers, buy
    what's wanted, share one piece of news in social talk, small talk,
    goodbye; replan changes nothing (no affinity drift without an LLM).
    Claude's speaker/planner have the same signatures (see §3 LLM
    integration) — the engine doesn't know which one it runs.
  - `GET /conversations?active=&limit=` returns transcripts with
    `replans` (stage 4's live panel source); TALK lines already show in
    the village log.
- **TRADE v2 negotiation** (`backend/sim/negotiation.py`, 2026-07-16):
  LLM seller/buyer reactions with counters clamped to 70–130% of base.
  **Unused since stage 1b** — prices come from the economy rules, and
  haggling happens through conversation offers (counter = new offer).
  Kept for reference only.
- **Economy** (`backend/sim/economy.py`, stage 1b, since 2026-10-16) —
  rules and tuned numbers in one file, pure functions:
  - *Hunger* grows 8/h awake, 3/h asleep; at 50 a villager eats a carried
    meal (−50). Everyone tops up to 3 meals when food is on sale nearby,
    in practice on arriving at the Inn in the evening.
  - *Production*, once per in-game hour of WORK: Farmer → 1 wheat (needs a
    farming tool; 2 wear per batch, ~8 days per tool), Blacksmith → 1
    farming_tools, Innkeeper → 2 food from 1 wheat. Producers stop at a
    store cap (wheat 20, tools 3, food 16) — a full store also stops tool
    wear.
  - *Who sells where:* producers only at their own workplace, the Merchant
    anywhere. Never sold: own 3 meals, the innkeeper's cooking wheat, the
    farmer's spare tool.
  - *Prices* (`prices.py` base): the Merchant buys stock wholesale (×0.8)
    and sells retail (×1.2); everything else at base. Money is conserved,
    so the flows must balance: food spend = tool spend = 0.4 × wheat base
    × wheat volume (derivation in `economy.py`). Tuned with
    `tools/simulate.py`: wheat 10→15c, tool wear 2/batch; 28 days end
    within ±6c/day for everyone except one-off effects of starting stock.
  - *Tick order:* everyone's hunger grows → every active conversation
    says its next line (bedtime ends it) → everyone not talking: walk →
    just woke up: plan the day → eat → start a conversation if there's a
    reason → urgent errand
    (hungry with no food, broken tool: go where it's sold, if someone
    awake sells it) → schedule block.
  - State: `AgentState.needs` JSON (`hunger`, `tool`), defaults via
    `economy.needs_of()` for NULL rows; shown as gauges on the cards.
- **Time:** **1 tick = 1 in-game minute** (60 ticks/hour, 1440/day, since
  2026-10-16); day/hour/minute derived from `SimState.tick`. With one tick
  per 60 real seconds the village runs at real-time speed. History:
  1 h/tick made 1-tile-per-tick travel take two in-game days; 5 min/tick
  still took 4 hours from the Farm to the Inn (48 tiles), which broke the
  daily routine — now it's 48 minutes (Smithy 36, Market 31). WORK yields
  its product once per in-game hour (on the minute-0 tick).
  `POST /tick?count=N` advances up to one day per call; `GET /time`,
  `GET /history` for inspection (`notable=true` filters to trades and
  dialogue server-side — at 1 min/tick the latest 50 raw rows only cover
  ~12 minutes, so client-side filtering left the log empty). Nothing hard-codes the scale outside
  `backend/config.py`: `GET /status` reports `minutes_per_tick` and the
  frontend's `clock.js` / tick buttons use it.
- **Schedules** (`backend/sim/schedule.py`, stage 1a, since 2026-10-16):
  each agent's `daily_plan` is `{"days": [...], "blocks": [...]}`; a block
  is `start`/`end` (absolute ticks, so SLEEP can cross midnight), `do`
  (WORK | SOCIAL | SLEEP | VISIT), `at`, `with`, `why`, `source` (routine
  | ai). `ensure()` lays the job's routine for today and tomorrow in the
  gaps AI blocks leave and drops finished blocks; `insert()` adds a block
  that wins and splits whatever it overlaps. Routines: Farmer, Blacksmith
  WORK 06–18 at the workplace, SOCIAL 18–22 at the Inn, SLEEP 22–06 at
  home (= the workplace for now); Merchant VISIT Farm 06–09 (buy wheat),
  WORK at the Market 09–18, SOCIAL at the Inn 18–22 (sells it there);
  Innkeeper WORK 06–22, SLEEP 22–06. The tick engine executes the current
  block each tick (walk to its place first); `GET /villagers` includes it
  as `activity`. Days already laid keep the routine they were laid with —
  a routine change shows up from the next unlaid day.
  - *Planner edits* (`apply_ops`, stage 3): ≤ 3 ops per call — `insert`
    (day, from, to, do, at, with, why), `cancel` (block id), `move`
    (block id → new day/from/to). Each is validated on its own and
    rejected with a reason: unknown place/person/block, off the 5-minute
    grid, in the past or beyond the end of tomorrow, WORK away from the
    workplace, > 5 appointments, or a night (noon to noon) left with < 6 h
    of SLEEP. An inserted block keeps what it cut away in `covers`, so
    cancelling or moving it gives that back; cancelling a routine block
    leaves free time (no block: the villager stays put, and it counts as
    leisure for chatting). Planners see blocks as `for_planner()` lists
    with ids `b<start tick>`.
  - *Wake-up plan* (stage 3): when a villager was asleep last tick and the
    sleep block is over, it plans the day once (`daily_plan["planned"]`
    records the days): one planner call sees today's and tomorrow's
    blocks, its memories and needs, and may edit the schedule (validated
    as above). Templates keep the routine. Checked before eating or
    talking, so a hungry wake-up still plans.
- **Who advances time** (`backend/sim/runner.py`, since 2026-10-15):
  `TICK_INTERVAL_SECONDS > 0` starts a background loop in the FastAPI
  lifespan — one tick every N real seconds, fixed rate with no catch-up
  bursts, first tick one interval after startup, a failed tick is logged
  and skipped, shutdown waits for the in-flight tick. Default `0` = no
  loop (local dev). `MANUAL_TICK_ENABLED=0` makes `POST /tick` return 403
  — required on the public server, since every tick costs LLM calls.
  Loop and `/tick` share one lock, so ticks never overlap. `GET /status`
  reports both settings; the frontend swaps the tick buttons for a LIVE
  badge when manual ticking is off. Single uvicorn worker only — each
  worker would run its own loop.

### LLM integration
- `backend/llm/client.py` — OpenAI-compatible `/chat/completions` via httpx.
  Endpoint/model come from env vars (`LLM_BASE_URL`, `LLM_MODEL`); defaults
  to LM Studio at `http://localhost:1234/v1` (see `backend/config.py`).
  Nothing uses it since the per-tick decider was removed (stage 1a);
  kept for running a local model later.
- **Claude for conversations** (stage 3, since 2026-10-16). LLM calls
  happen only for conversation lines, the planner after a conversation
  and the wake-up plan — ~115 calls per in-game day with 4 villagers.
  - `backend/llm/providers.py` picks the (speaker, planner) pair once at
    import: templates unless `CONVERSATION_LLM=claude` (default
    `template`, so local "+1 day" clicks cost nothing). Each Claude call
    that fails falls back to the template for that one line or plan.
  - `backend/llm/claude.py`: official `anthropic` SDK, structured outputs
    (`prompts.TURN_SCHEMA` / `PLAN_SCHEMA`), the fixed system prompt
    cache-marked (≈60% of input tokens are cache reads), effort `low`,
    per-model thinking (Haiku `disabled`, Sonnet `between_tools`, Opus
    5.5 can't disable it — omitted). Opus/Sonnet requests go through the
    beta endpoint with `fallbacks: "default"` (`server-side-fallback-
    2026-07-01`): a falsely refused request is re-run server-side on a
    fallback model. Refusal, `max_tokens`, API errors, unparseable JSON
    and the daily cap all raise `ClaudeUnavailable` → template.
  - `backend/llm/prompts.py` renders views into prompts (English) and maps
    replies back (`share` comes back as a news id).
  - Settings: `VILLAGE_CLAUDE_MODEL` (default `claude-opus-5-5`, chosen
    2026-10-16), `VILLAGE_CLAUDE_EFFORT` (`low`),
    `VILLAGE_CLAUDE_TIMEOUT_SECONDS` (30, one retry),
    `LLM_DAILY_CALL_LIMIT` (500 calls per UTC day, then templates).
    `ANTHROPIC_API_KEY` comes from the gitignored `.env` (loaded by
    `config.py`) locally, an EnvironmentFile on the server.
  - `backend/llm/usage.py` counts today's calls, tokens and estimated
    cost per model price (Opus 5.5 cache reads are 0.05× input, the
    others 0.1×); `GET /status` shows it under `llm`.

### Currency
- **Copper-based economy**, with **1 gold = 200 copper** (`backend/utils/currency.py`).
  This rate was chosen to balance historical plausibility against
  computational simplicity (the ratio was researched before it was committed).

### Memory / retrieval (live since 2026-07-16)
- **Short-term memory:** every notable event is written to
  `AgentState.short_term_memory` (ring buffer, newest 50) by
  `remember()` in `backend/memory/short_term.py` — arrivals, trades (both
  sides: wheat/tools importance 3, routine food purchases 1), a broken
  farming tool (2), hourly WORK output (1), news heard ("X told me: …", 1),
  a one-line summary of each social conversation (1). Memories carry a
  `told` list so news isn't repeated to the same person.
- **Prompt selection** (`memory_lines` in `backend/memory/selection.py`,
  moved out of the old decider): top-8 by `importance × 6 in-game hours −
  age`, duplicates collapsed, shown chronologically. Recency alone drowned
  a trade under one evening of repeated greetings — that's why importance
  exists. Feeds the speaker and planner prompts; planners add their own
  one-line memory after each conversation and on waking.
- **ChromaDB long-term store is OPTIONAL** (`backend/memory/store.py`):
  install `chromadb` on the dev PC only — far too heavy for the 1 GB
  deployment box, which degrades gracefully to a null store. When
  active it persists all memories to `data/chroma/` (gitignored) and
  appends top-3 semantically relevant older memories to the prompt.
  Kill switch: `VECTOR_MEMORY=0`. First use downloads the MiniLM ONNX
  embedding model (~80 MB) to `~/.cache/chroma/`.
- In-game clock helpers live in `backend/sim/clock.py` (not
  tick_engine) so memory selection and schedules can use them without a
  circular import.

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

### Deployment — currently offline
- 2026-07-14 → 07-27 the sim ran on a shared Oracle Cloud instance as a
  systemd service (rule-based only, no LLM). It was shut down there on
  2026-07-27 to isolate other workloads on that box, and must not go back.
- Redeploy target: a **dedicated** Oracle Cloud instance (1 GB RAM,
  Ubuntu 26.04 / Python 3.14), base-hardened 2026-10-15, app not
  installed yet. Plan: server-driven ticks every 60 s with manual ticks
  off (§3), the Claude API key in a root-only EnvironmentFile, a dedicated
  Linux user with systemd sandboxing — stage 5 of the §6 redesign.
- **Addresses, SSH access, ports and procedures live in
  `CLAUDE.local.md`** (gitignored — this repo is public, so no
  infrastructure details belong in committed files).

---

## 6. Roadmap — next planned work (in order)

Backend world + movement first; frontend after.

1. ~~**Tile-based open-world map**~~ ✅ done — 100×50 grid, walkable/resource
   tiles, building interiors (`backend/world/`).
2. ~~**A\* pathfinding**~~ ✅ done — agents move 1 tile per tick.
3. ~~**Structured action types**~~ ✅ done — all six actions work; TRADE
   settles via the v1 core, with **v2 LLM price negotiation** layered on
   top since 2026-07-16 (see §3).
4. ~~**Time system**~~ ✅ done — 1 tick = 5 in-game minutes (`SimState.tick`).
5. ~~**Frontend v1**~~ ✅ done (2026-07-15, pulled ahead of memory for
   portfolio visibility) — React + Vite in `frontend/`: canvas map
   renderer, villager cards, filtered event log (TALK dialogue + TRADE
   copper flows), tick controls with auto-run. Dev: vite on :5173
   proxies API paths to :8000 (`.claude/launch.json` has both servers).
   Prod: **`frontend/dist` is committed** and FastAPI serves it at `/`
   via StaticFiles (mounted last, API routes win; old `/` status JSON
   moved to `/health`) — the 1 GB deployment box needs no Node.js.
6. ~~**Agent memory**~~ ✅ done (2026-07-16) — observations/conversations
   → `short_term_memory` with importance-weighted prompt selection;
   ChromaDB retrieval as an optional layer (see §3 Memory).
7. **Hybrid AI redesign** — agreed 2026-10-16, next up. Design and build
   order below. Absorbs the old "villager detail view" polish item.
8. **Frontend polish, later** — day/night tint, smoother movement
   animation, mobile layout.

### Hybrid AI redesign (agreed 2026-10-16)

**Why.** A 30-situation comparison (Claude Haiku 5.5 / Sonnet 5.5 / Opus
5.5 on the real decider + negotiation prompts, structured outputs, effort
low) showed:
- Per-tick LLM decisions are the cost driver: ~870 input / ~55 output
  tokens per call; at one tick per 60 s the upper bound was roughly
  $21 / $423 / $855 per month.
- No model ever initiated a TRADE in 22 decisions — the prompt lists no
  prices or sellers, and nothing in the world consumes goods.
- Model differences show mostly in dialogue and negotiation, the part
  visitors actually see.

**Design.**
- **Behavior is code.** Each agent follows a schedule of time blocks in
  `AgentState.daily_plan`: `day`, `from`, `to`, `do` (WORK | SOCIAL |
  SLEEP | VISIT), `at` (building), optional `with` (person → an
  appointment), `why`. Code lays the job's default routine each day and
  executes the current block every tick; urgent needs (hunger) override
  the schedule. Replaced the per-tick LLM call of the old decider.
- **Economy loop.** Hunger (2–3 meals a day, buy food when out); cooking
  consumes wheat; farming_tools wear out with WORK (no tool → no
  farming); the Merchant buys surpluses and sells where stock is short
  (Farm → Market → Inn round). Stock thresholds yield "needs" and "for
  sale". Recipes, wear rates and prices get tuned by offline simulation.
- **The LLM is used only for conversations,** turn-based: one line per
  tick, written by the speaker from its own view (own profile, memories,
  affinity toward the partner in words, the usual price list, transcript,
  pending offer). Output (JSON schema): `line`, `end`, `offer`
  {sell|buy, item, quantity, price} (a counter is a new offer),
  `response` accept|reject. Accept settles at once through the existing
  TRADE core (stock/funds checks, 70–130% clamp). Max 8 lines; an
  unanswered offer lapses.
- **Conversation start is code:** 1:1, same building, both awake, not
  already talking, per-pair cooldown (~2 in-game hours). The initiator
  carries a reason into its first line: trade (needs what the other
  sells), appointment, news (an unshared memory of importance ≥ 2), or
  chat (chance during SOCIAL blocks).
- **After a conversation, each participant gets one replan call** (built
  as a reusable "replan on event"): it first judges whether anything
  requires a schedule change, then returns ≤ 3 ops (insert / cancel /
  move), a one-line memory with importance 1–3, and an affinity change
  (−2..+2). Code validates ops: real places and people, 5-minute grid,
  horizon = end of tomorrow, an inserted block wins and splits overlaps,
  ≤ 5 appointments per agent. Only a 6-hour sleep floor is guaranteed —
  the AI may shorten or skip WORK, and the economy makes them pay.
- **No LLM → templates.** Template lines offer and accept at base price
  and replan changes nothing, so the village still runs.
- **Data model.** `AgentState.needs` (JSON), a `Relationship` table
  (pair affinity, last talk tick), a `Conversation` table (participants,
  lines, offers, outcome), schedule in `daily_plan`. New tables come from
  `create_all`, new columns from `database.add_missing_columns` (additive
  only) — no world reset needed.
- **Frontend.** Speech bubbles over speakers (and villagers spread out
  inside buildings instead of overlapping), a live "talking now" panel
  that grows one line per tick with offer chips; then a scene-grouped
  log and a villager detail view (schedule timeline incl. the AI's `why`,
  needs, relationships, memories).

**Build order** — every stage runs and gets committed on its own:
0. ~~Record this design.~~ ✅ 2026-10-16
1. a) ~~Schedule-driven behavior.~~ ✅ 2026-10-16 — needed no schema
   change (`daily_plan` already existed); the time scale moved to
   1 min/tick on the way (see §3 Time), which reset the local world.
   b) ~~Economy loop.~~ ✅ 2026-10-16 — `needs` JSON column added by the
   new additive auto-migration (`database.add_missing_columns`: missing
   columns are ALTERed in, so deploys keep the world), numbers tuned
   with `tools/simulate.py` (see §3 Economy).
2. ~~Conversation engine with template lines.~~ ✅ 2026-10-16 (see §3
   Conversations). All buying now happens in trade conversations. Sim:
   ~15 conversations per in-game day → with an LLM ≈ 40 line calls + 30
   replan calls per in-game day.
3. ~~Claude integration.~~ ✅ 2026-10-16 (see §3 LLM integration), plus a
   wake-up plan (one planner call per villager per morning) and planner
   edits actually applied. **Model: Claude Opus 5.5**, chosen from a paid
   comparison — each model ran the same world for 2 in-game days
   (`tools/simulate.py --llm claude --export`; the report stays local):
   - Cost per in-game day (= per real day at 60 s ticks): Haiku 5.5
     $0.03, Sonnet 5.5 $0.31, Opus 5.5 ≈ $0.65 (~$19/month).
   - Haiku: cheap but incoherent — re-offered closed deals (duplicate
     trades), misread its own numbers, invented stories and churned
     schedules around them. Sonnet: natural haggling, rarely edits
     schedules, affinity +1 after nearly every talk. Opus: most coherent —
     keeps agreed prices across conversations, affinity −1 when cheated,
     schedule edits that follow from promises.
   - Follow-ups the comparison exposed (all models): affinity inflation;
     ale purchases stored at importance 3 and retold as news; the speaker
     view doesn't list deals already settled in the conversation; wake-up
     plans rarely change anything (fine — 4 calls a day).
4. Frontend: bubbles + live panel first.
5. Deploy to a dedicated instance: server-driven ticks every 60 s, manual
   ticks off.

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
- **On the Windows dev PC, ticks are slow when LM Studio is off**: the
  firewall silently drops connects to the closed port 1234, so every LLM
  attempt burns the full `LLM_CONNECT_TIMEOUT` (2 s) instead of failing
  instantly. Set `LLM_CONNECT_TIMEOUT=0.2` (or start LM Studio) for
  snappy local dev. On Linux the connect is refused immediately.
- **Claude Code exports `CLAUDE_EFFORT` (e.g. `xhigh`) into every shell it
  starts.** Our settings used to read that same name, so every API call
  from a Claude Code session failed with a 400 (Haiku with thinking off
  can't take `xhigh`). Hence the `VILLAGE_CLAUDE_*` names — keep project
  env vars prefixed.
- **Always get DB sessions via `Depends(get_db)` in FastAPI routes.**
  Hand-calling `next(get_db())` skips the generator's `finally`, leaks
  the session, and under frontend polling exhausts the connection pool
  (`QueuePool limit reached` → HTTP 500). Bitten once already.

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
