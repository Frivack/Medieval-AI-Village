import { formatCopper, tickToClock } from "../currency.js";

// The interesting events: dialogue lines and money changing hands.
// MOVE/WORK/REST spam is filtered client-side to keep the feed readable.
const QUIET_ACTIONS = new Set(["MOVE", "REST", "OBSERVE", "WORK"]);

export default function HistoryFeed({ history, nameById }) {
  const rows = history.filter(
    (r) => !QUIET_ACTIONS.has(r.action) || r.dialogue
  );
  return (
    <section className="history-feed">
      <h2>Village log</h2>
      {rows.length === 0 && <p className="empty">Nothing has happened yet…</p>}
      <ul>
        {rows.map((r, i) => (
          <li key={i} className={`ev ev-${r.action.toLowerCase()}`}>
            <span className="ev-time">{tickToClock(r.tick)}</span>
            <span className="ev-agent">{nameById[r.agent_id] ?? r.agent_id}</span>
            {r.action === "TRADE" ? (
              <span className={r.copper_change >= 0 ? "gain" : "spend"}>
                {r.copper_change >= 0 ? "earned" : "spent"}{" "}
                {formatCopper(Math.abs(r.copper_change))}
              </span>
            ) : r.dialogue ? (
              <span className="ev-dialogue">“{r.dialogue}”</span>
            ) : (
              <span className="ev-action">{r.action.toLowerCase()}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
