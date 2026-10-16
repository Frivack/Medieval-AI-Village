"""Offline simulation: run the village for N in-game days on a throwaway DB
and report how the economy behaves. No server, no LLM, no effect on
data/village.db. Used to tune backend/sim/economy.py and prices.py.

usage (repo root):  python tools/simulate.py [--days 14] [--hourly] [--db PATH]
"""
import argparse
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
    args = ap.parse_args()

    # Must happen before anything under backend/ is imported: config.py
    # reads these at import time.
    db = Path(args.db) if args.db else Path(tempfile.mkdtemp()) / "sim.db"
    os.environ["VILLAGE_DB_PATH"] = str(db)
    os.environ.setdefault("VECTOR_MEMORY", "0")
    os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:9/v1")  # closed port: instant fallback
    os.environ.setdefault("LLM_CONNECT_TIMEOUT", "0.2")
    sys.path.insert(0, str(ROOT))

    from backend.agents.loader import load_agents_from_json
    from backend.config import TICKS_PER_DAY
    from backend.database import AgentState, Conversation, SessionLocal, init_db
    from backend.sim.tick_engine import run_tick

    init_db()
    load_agents_from_json()
    ticks = int(args.days * TICKS_PER_DAY)
    print(f"simulating {args.days:g} in-game days ({ticks} ticks) on {db}\n")

    by_hour = defaultdict(Counter)      # (agent, hour) -> "status@location" counts
    daily = defaultdict(lambda: defaultdict(Counter))  # day -> agent -> counters
    max_hunger = defaultdict(dict)      # day -> agent -> max hunger that day
    flows = defaultdict(lambda: [0, 0, 0])  # (item, seller, buyer) -> [deals, units, copper]
    work_events = Counter()             # (agent, event) e.g. "no tool"
    problems = Counter()
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

    snapshot(0)
    for _ in range(ticks):
        t = run_tick()
        day = t["day"]
        for r in t["results"]:
            n, detail = r["agent"], r["detail"]
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
            if r["action"] == "OBSERVE" and detail.startswith(("no path", "nothing planned", "wanted")):
                problems[(n, detail)] += 1
        if t["hour"] == 23 and t["minute"] == 59:
            snapshot(day)

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
        print(f"  {n:<9} {first[n][0]:>6} -> {last[n][0]:>6}  ({delta:+d}, {delta / max(1, max(snapshots)):+.0f}/day)")

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

    talking = Counter()
    for day in daily:
        for n in daily[day]:
            talking[n] += daily[day][n]["talking_min"]
    days = max(1, max(snapshots))
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
    print(f"  -> with an LLM speaker that would be ~{llm_lines:.0f} line calls "
          f"+ ~{2 * len(convos) / days:.0f} replan calls per in-game day")

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


if __name__ == "__main__":
    main()
