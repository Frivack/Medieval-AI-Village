"""Offline simulation: run the village for N in-game days on a throwaway DB
and print what everyone did, hour by hour. No server, no LLM, no effect on
data/village.db. Stage 1b uses this to tune the economy's numbers.

usage (repo root):  python tools/simulate.py [--days 3] [--db PATH]
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
    ap.add_argument("--days", type=float, default=3, help="in-game days to run")
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
    from backend.database import AgentState, SessionLocal, init_db
    from backend.sim.tick_engine import run_tick

    init_db()
    load_agents_from_json()
    ticks = int(args.days * TICKS_PER_DAY)
    print(f"simulating {args.days:g} in-game days ({ticks} ticks) on {db}")

    by_hour = defaultdict(Counter)        # (agent, hour) -> "status@location" counts
    problems = Counter()                   # (agent, detail) for anything that looks stuck
    arrivals = defaultdict(list)           # agent -> "Day d hh:mm" of each arrival at the Inn
    trades = Counter()
    for _ in range(ticks):
        t = run_tick()
        for r in t["results"]:
            by_hour[(r["agent"], t["hour"])][f"{r['status']}@{r['location']}"] += 1
            if r["action"] == "OBSERVE" and r["detail"].startswith(("no path", "nothing planned", "wanted")):
                problems[(r["agent"], r["detail"])] += 1
            if r["detail"] == "arrived at Inn":
                arrivals[r["agent"]].append(f"D{t['day']} {t['hour']:02d}:{t['minute']:02d}")
            if r["action"] == "TRADE":
                trades[r["agent"]] += 1

    names = sorted({a for a, _ in by_hour})
    print("\nmost common state per hour of day, across all simulated days:")
    print("hour  " + "".join(f"{n:<24}" for n in names))
    for hour in range(24):
        cells = []
        for n in names:
            state, count = by_hour[(n, hour)].most_common(1)[0]
            total = sum(by_hour[(n, hour)].values())
            cells.append(f"{state} {100 * count // total}%".ljust(24))
        print(f"{hour:02d}    " + "".join(cells))

    print("\narrivals at the Inn:")
    for n in names:
        print(f"  {n:<9} {', '.join(arrivals[n]) or '-'}")
    print("\nproblems (stuck / no path / nothing planned):")
    for (n, detail), count in sorted(problems.items()) or [((None, None), 0)]:
        print(f"  {n}: {detail} x{count}" if n else "  none")

    session = SessionLocal()
    try:
        print("\nend state:")
        for a in session.query(AgentState).order_by(AgentState.id):
            print(f"  {a.name:<9} {a.wealth:>6}c  trades {trades[a.name]:>3}  {a.inventory}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
