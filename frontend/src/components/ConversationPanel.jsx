import { useEffect, useRef } from "react";
import { formatCopper } from "../currency.js";

// "Talking now": every conversation in progress, growing one line per
// tick, with what each line did to the deal on the table. Conversations
// are rare (~15 a day), so when nobody talks the last one that ended
// stays here, folded.

export const REASON = { trade: "trade", appointment: "appointment", news: "news", chat: "chat" };
export const ENDED = { goodbye: "said goodbye", "max lines": "talked it out", bedtime: "bedtime" };

// "7s 2c (18c each)": the unit price in plain copper reads easier than
// "1s 8c each".
export function amount(price, quantity) {
  const each = quantity > 1 ? ` (${+(price / quantity).toFixed(1)}c each)` : "";
  return `${formatCopper(price)}${each}`;
}

// One line of a conversation with what it did to the deal on the table.
// Shared with the scene log.
export function Line({ line, deal, colors }) {
  const o = line.offer;
  return (
    <li className="talk-line">
      <span className="talk-speaker" style={{ "--accent": colors[line.speaker] }}>{line.speaker}</span>
      <span className="talk-text">{line.text}</span>
      {(o || line.response || deal || line.note) && (
        <span className="talk-chips">
          {o && (
            <span className="chip offer">
              {o.kind === "sell" ? "offers to sell" : "offers to buy"} {o.quantity}{" "}
              {o.item.replace("_", " ")} · {amount(o.price, o.quantity)}
            </span>
          )}
          {line.response === "accept" && <span className="chip accept">✓ accepts</span>}
          {line.response === "reject" && <span className="chip reject">✗ refuses</span>}
          {deal && (
            <span className="chip deal">
              deal: {deal.buyer} buys {deal.quantity} {deal.item.replace("_", " ")} for{" "}
              {amount(deal.price, deal.quantity)}
            </span>
          )}
          {line.note && <span className="chip reject">{line.note}</span>}
        </span>
      )}
    </li>
  );
}

function Conversation({ c, colors }) {
  const listRef = useRef(null);
  // Keep the newest line in view as the conversation grows.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [c.lines.length]);
  const item = c.lines.find((l) => l.offer)?.offer.item;
  return (
    <article className={`talk ${c.status}`}>
      <header className="talk-head">
        <strong>{c.a} ↔ {c.b}</strong>
        <span className="talk-meta">
          {c.place} · {REASON[c.reason] ?? c.reason}
          {c.reason === "trade" && item ? ` (${item.replace("_", " ")})` : ""} · from {c.started.replace(/^Day \d+ /, "")}
          {c.status === "ended" && ` · ${ENDED[c.end_reason] ?? c.end_reason}`}
        </span>
      </header>
      <ol className="talk-lines" ref={listRef}>
        {c.lines.map((line, i) => (
          <Line key={i} line={line} colors={colors}
                deal={line.response === "accept" ? c.deals.find((d) => d.tick === line.tick) : null} />
        ))}
      </ol>
    </article>
  );
}

export default function ConversationPanel({ conversations, colors }) {
  const active = conversations.filter((c) => c.status === "active");
  const last = conversations.find((c) => c.status === "ended");
  return (
    <section className="talk-panel" aria-live="polite">
      <h2>Talking now</h2>
      {active.map((c) => <Conversation key={c.id} c={c} colors={colors} />)}
      {active.length === 0 && (
        <>
          <p className="empty">No one is talking right now.</p>
          {last && (
            <details className="talk-last">
              <summary>Last conversation: {last.a} ↔ {last.b} at {last.place}, ended {last.ended}</summary>
              <Conversation c={last} colors={colors} />
            </details>
          )}
        </>
      )}
    </section>
  );
}
