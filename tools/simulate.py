"""Offline simulation: run the village for N in-game days on a throwaway DB
and report how the economy behaves. No server, no effect on
data/village.db. Used to tune backend/sim/economy.py and prices.py, and
(with --llm claude) to compare models on the real conversation prompts.

usage (repo root):  python tools/simulate.py [--days 14] [--hourly] [--db PATH]
                    [--llm claude --model claude-haiku-5-5 --max-cost 0.50]
--llm claude makes PAID API calls (key from .env); --max-cost stops the
run once the estimated spend reaches that many dollars. --export writes
the run as JSON: every speaker/planner call (with fallbacks), the
conversations, and usage — for comparing models side by side.
"""
import argparse
import json
import logging
import os
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=14, help="in-game days to run")
    ap.add_argument("--hourly", action="store_true",
                    help="also print everyone's most common state per hour of day")
    ap.add_argument("--transcripts", type=int, default=0, metavar="N",
                    help="also print the last N conversations line by line")
    ap.add_argument("--db", help="DB file to use (default: a fresh temp file)")
    ap.add_argument("--llm", choices=["template", "claude"], default="template",
                    help="who writes conversation lines and plans (claude = paid API calls)")
    ap.add_argument("--model", help="Claude model id (default: config.CLAUDE_MODEL)")
    ap.add_argument("--max-cost", type=float, default=1.0, metavar="USD",
                    help="with --llm claude: stop once the estimated spend reaches this")
    ap.add_argument("--export", metavar="PATH", help="write the run's calls and conversations as JSON")
    args = ap.parse_args()

    # Must happen before anything under backend/ is imported: config.py
    # reads these at import time.
    db = Path(args.db) if args.db else Path(tempfile.mkdtemp()) / "sim.db"
    os.environ["VILLAGE_DB_PATH"] = str(db)
    os.environ.setdefault("VECTOR_MEMORY", "0")
    os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9/v1")  # closed port: instant fallback
    os.environ.setdefault("LLM_CONNECT_TIMEOUT", "0.2")
    os.environ["CONVERSATION_LLM"] = args.llm
    if args.model:
        os.environ["VILLAGE_CLAUDE_MODEL"] = args.model
    sys.path.insert(0, str(ROOT))

    from backend.agents.loader import load_agents_from_json
    from backend.config import CLAUDE_MODEL, TICKS_PER_DAY
    from backend.database import AgentState, Conversation, SessionLocal, init_db
    from backend.llm import claude, usage
    from backend.sim import tick_engine
    from backend.sim.clock import format_clock
    from backend.sim.tick_engine import run_tick

    # Log every speaker/planner call the engine makes (it reads these two
    # module globals on each call). A fallback shows up as a warning from
    # backend.llm.providers during the call.
    calls, fallbacks = [], []

    class _Fallbacks(logging.Handler):
        def emit(self, record):
            fallbacks.append(record.getMessage())

    logging.basicConfig(level=logging.WARNING, format="  [%(name)s] %(message)s")  # show fallbacks
    logging.getLogger("backend.llm.providers").addHandler(_Fallbacks())

    def logged(kind, fn):
        def call(view):
            before = len(fallbacks)
            out = fn(view)
            entry = {"kind": kind, "event": view.get("event", "turn"), "tick": view["time"]["tick"],
                     "clock": format_clock(view["time"]["tick"]), "who": view["me"]["name"],
                     "partner": (view.get("partner") or {}).get("name"),
                     "fallback": fallbacks[before:] or None}
            if kind == "plan":
                entry["answer"] = out
                if view["event"] == "wake_up":
                    entry["saw"] = {"memories": view["memories"], "schedule": view["schedule"],
                                    "needs": view["me"]["needs"], "wealth": view["me"]["wealth"],
                                    "inventory": view["me"]["inventory"]}
            calls.append(entry)
            return out
        return call

    tick_engine.SPEAK = logged("turn", tick_engine.SPEAK)
    tick_engine.PLAN = logged("plan", tick_engine.PLAN)

    init_db()
    load_agents_from_json()
    ticks = int(args.days * TICKS_PER_DAY)
    llm = args.llm == "claude"
    print(f"simulating {args.days:g} in-game days ({ticks} ticks) on {db}"
          + (f" with {CLAUDE_MODEL}, stop at ${args.max_cost:.2f}" if llm else "") + "\n")

    by_hour = defaultdict(Counter)      # (agent, hour) -> "status@location" counts
    daily = defaultdict(lambda: defaultdict(Counter))  # day -> agent -> counters
    max_hunger = defaultdict(dict)      # day -> agent -> max hunger that day
    flows = defaultdict(lambda: [0, 0, 0])  # (item, seller, buyer) -> [deals, units, copper]
    work_events = Counter()             # (agent, event) e.g. "no tool"
    problems = Counter()
    free_time = Counter()               # agent -> minutes with no block (a planner cancelled it)
    wake_plans = []                     # (tick, agent, record) from the wake-up planner
    spent = {"carry": {}, "last": usage.snapshot()}   # usage resets at UTC midnight
    snapshots = {}                      # day -> agent -> (wealth, inventory)
    names = []

    def snapshot(day):
        session = SessionLocal()
        try:
            snapshots[day] = {a.name: (a.wealth, dict(a.inventory or {}))
                              for a in session.query(AgentState).order_by(AgentState.id)}
            names[:] = list(snapshots[day])
        finally:
            session.close()

    def llm_totals() -> dict:
        now = usage.snapshot()
        if now["date"] != spent["last"]["date"]:
            for k, v in spent["last"].items():
                if k != "date":
                    spent["carry"][k] = spent["carry"].get(k, 0) + v
        spent["last"] = now
        return {k: v + spent["carry"].get(k, 0) for k, v in now.items() if k != "date"}

    snapshot(0)
    ran = 0
    for _ in range(ticks):
        t = run_tick()
        ran += 1
        day = t["day"]
        if llm:
            totals = llm_totals()
            if t["minute"] == 0:
                print(f"  {format_clock(t['tick'])}  calls {totals['calls']:>4}  failures "
                      f"{totals['failures']:>3}  ${totals['cost_usd']:.4f}", flush=True)
            if totals["cost_usd"] >= args.max_cost:
                print(f"\nstopped: estimated spend ${totals['cost_usd']:.4f} reached "
                      f"--max-cost ${args.max_cost:.2f} at {format_clock(t['tick'])}")
                break
            # The circuit breaker opens after this many API errors and then
            # records no more, so it's also where "nothing works" shows.
            if totals["calls"] == 0 and totals["failures"] >= claude.BREAKER_FAILURES:
                print(f"\nstopped: the first {claude.BREAKER_FAILURES} calls all failed "
                      "(see the warnings above)")
                break
        for r in t["results"]:
            n, detail = r["agent"], r["detail"]
            if r.get("plan"):
                wake_plans.append((t["tick"], n, r["plan"]))
            if detail.startswith("free time"):
                free_time[n] += 1
            by_hour[(n, t["hour"])][f"{r['status']}@{r['location']}"] += 1
            max_hunger[day][n] = max(max_hunger[day].get(n, 0), r["hunger"] or 0)
            if (r["hunger"] or 0) >= 100:
                daily[day][n]["starving_min"] += 1
            if r["action"] == "EAT":
                daily[day][n]["meals"] += 1
            if r["status"] == "talking":
                daily[day][n]["talking_min"] += 1
            if detail.startswith("set off to"):
                daily[day][n]["errands"] += 1
            for tr in r.get("trades", []):
                if tr["copper_change"] < 0:          # count each deal once, on the buyer's side
                    f = flows[(tr["item"], tr["seller"], tr["buyer"])]
                    f[0] += 1
                    f[1] += tr["quantity"]
                    f[2] += -tr["copper_change"]
            if r["action"] == "WORK" and not detail.startswith(("working", "produced")):
                work_events[(n, detail.split(" at ")[0])] += 1
            if r["action"] == "OBSERVE" and detail.startswith(("no path", "wanted")):
                problems[(n, detail)] += 1
        if t["hour"] == 23 and t["minute"] == 59:
            snapshot(day)
    if ran < ticks:
        snapshot(day)                   # partial last day
    days = max(ran, 1) / TICKS_PER_DAY    # in-game days actually run

    if args.hourly:
        print("most common state per hour of day:")
        print("hour  " + "".join(f"{n:<24}" for n in names))
        for hour in range(24):
            cells = []
            for n in names:
                state, count = by_hour[(n, hour)].most_common(1)[0]
                cells.append(f"{state} {100 * count // sum(by_hour[(n, hour)].values())}%".ljust(24))
            print(f"{hour:02d}    " + "".join(cells))
        print()

    def inv_short(inv):
        keys = [("wheat", "w"), ("food", "f"), ("farming_tools", "t")]
        return " ".join(f"{abbr}{inv.get(k, 0)}" for k, abbr in keys)

    print("end of each day: wealth (copper) | stock w=wheat f=food t=tools | meals eaten, max hunger")
    print("day " + "".join(f"{n:<34}" for n in names))
    for day in sorted(d for d in snapshots if d > 0):
        cells = []
        for n in names:
            wealth, inv = snapshots[day][n]
            c = daily[day][n]
            starving = f" STARVED {c['starving_min']}m" if c["starving_min"] else ""
            cells.append(f"{wealth:>6} {inv_short(inv):<12} {c['meals']}m h{max_hunger[day].get(n, 0):.0f}"
                         f"{starving}".ljust(34))
        print(f"{day:>3} " + "".join(cells))

    print("\nwealth change over the run:")
    first, last = snapshots[0], snapshots[max(snapshots)]
    for n in names:
        delta = last[n][0] - first[n][0]
        print(f"  {n:<9} {first[n][0]:>6} -> {last[n][0]:>6}  ({delta:+d}, {delta / days:+.0f}/day)")

    print("\ntrade flows (seller -> buyer: deals, units, copper):")
    for (item, seller, buyer), (deals, units, copper) in sorted(flows.items()):
        print(f"  {item:<14} {seller:>8} -> {buyer:<8} {deals:>4} deals {units:>4} units {copper:>6}c"
              f"  (~{copper / units:.1f}c each)")
    print("\nwork interruptions:")
    for (n, event), count in sorted(work_events.items()) or [((None, None), 0)]:
        print(f"  {n}: {event} x{count} hours" if n else "  none")
    errands = Counter()
    for day in daily:
        for n in daily[day]:
            errands[n] += daily[day][n]["errands"]
    print("urgent errands (left the schedule to buy):", dict(errands) or "none")
    print("stuck / no path:", dict(problems) or "none")
    print("free time (minutes with nothing planned):", dict(free_time) or "none")

    talking = Counter()
    for day in daily:
        for n in daily[day]:
            talking[n] += daily[day][n]["talking_min"]
    print("\nminutes spent talking per day:",
          {n: round(talking[n] / days) for n in names})

    session = SessionLocal()
    try:
        convos = session.query(Conversation).order_by(Conversation.id).all()
        people = {a.id: a.name for a in session.query(AgentState)}
    finally:
        session.close()
    print(f"conversations: {len(convos)} ({len(convos) / days:.1f}/day)")
    by_reason = defaultdict(list)
    for c in convos:
        by_reason[c.reason].append(c)
    for reason, cs in sorted(by_reason.items()):
        lines = [len(c.lines or []) for c in cs]
        deals = sum(len(c.deals or []) for c in cs)
        ends = Counter(c.end_reason for c in cs)
        print(f"  {reason:<11} {len(cs):>4}  avg {sum(lines) / len(lines):.1f} lines "
              f"(max {max(lines)})  deals {deals:>4}  ended: {dict(ends)}")
    llm_lines = sum(len(c.lines or []) for c in convos) / days
    print(f"  -> LLM calls per in-game day: ~{llm_lines:.0f} lines "
          f"+ ~{2 * len(convos) / days:.0f} replans + ~{len(wake_plans) / days:.0f} wake-up plans")

    changed = [(tk, n, rec) for tk, n, rec in wake_plans if rec["applied"] or rec["rejected"]]
    print(f"\nwake-up plans: {len(wake_plans)} ({len(wake_plans) - len(changed)} kept the routine)")
    for tk, n, rec in changed:
        print(f"  {format_clock(tk)} {n}: applied {rec['applied']} rejected {rec['rejected']}")
        if rec["memory"]:
            print(f"      memory: {rec['memory']}")
    replans = [(c, r) for c in convos for r in (c.replans or [])
               if r["applied"] or r["rejected"] or r["affinity"]]
    print(f"after-conversation replans that changed something: {len(replans)}")
    for c, r in replans:
        print(f"  #{c.id} {r['who']}: affinity {r['affinity']:+d} applied {r['applied']} "
              f"rejected {r['rejected']}")

    if llm:
        totals = llm_totals()
        per_day = totals["cost_usd"] / days
        print(f"\nLLM usage ({CLAUDE_MODEL}): {totals['calls']} calls, {totals['failures']} failures, "
              f"{totals['input_tokens']} in ({totals['cache_read_tokens']} cache read, "
              f"{totals['cache_write_tokens']} cache write) / {totals['output_tokens']} out tokens")
        print(f"  estimated ${totals['cost_usd']:.4f} = ${per_day:.4f} per in-game day "
              f"-> ~${30 * per_day:.2f}/month at 60 s ticks (1 in-game day = 1 real day)")

    for c in convos[-args.transcripts:] if args.transcripts else []:
        print(f"\n#{c.id} {people[c.a_id]} -> {people[c.b_id]} at {c.place} "
              f"({c.reason}, {c.end_reason})")
        for line in c.lines or []:
            extra = ""
            if line.get("offer"):
                o = line["offer"]
                extra += f"  [offer: {o['kind']} {o['quantity']} {o['item']} for {o['price']}c]"
            if line.get("response"):
                extra += f"  [{line['response']}]"
            if line.get("note"):
                extra += f"  [{line['note']}]"
            print(f"  {line['speaker']}: {line['text']}{extra}")
        for r in c.replans or []:
            print(f"    -> {r['who']}: affinity {r['affinity']:+d}, applied {r['applied']}, "
                  f"rejected {r['rejected']}, memory {r['memory']!r}")

    if args.export:
        first, last = snapshots[0], snapshots[max(snapshots)]
        export = {
            "llm": args.llm, "model": CLAUDE_MODEL if llm else None,
            "days": round(days, 3), "usage": llm_totals() if llm else None,
            "wealth": {n: [first[n][0], last[n][0]] for n in names},
            "stock": {n: last[n][1] for n in names},
            "flows": [{"item": i, "seller": s, "buyer": b, "deals": d, "units": u, "copper": c}
                      for (i, s, b), (d, u, c) in sorted(flows.items())],
            "conversations": [
                {"id": c.id, "a": people[c.a_id], "b": people[c.b_id], "place": c.place,
                 "reason": c.reason, "topic": c.topic, "started": format_clock(c.started_tick),
                 "ended": format_clock(c.ended_tick) if c.ended_tick is not None else None,
                 "end_reason": c.end_reason, "lines": c.lines or [], "deals": c.deals or [],
                 "replans": c.replans or []}
                for c in convos],
            "wake_plans": [{"tick": tk, "clock": format_clock(tk), "who": n, **rec}
                           for tk, n, rec in wake_plans],
            "calls": calls,
        }
        Path(args.export).write_text(json.dumps(export, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nexported to {args.export}")


if __name__ == "__main__":
    main()
