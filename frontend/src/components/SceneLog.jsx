import { amount, ENDED, Line, REASON } from "./ConversationPanel.jsx";

// The village's story so far: one scene per finished conversation, grouped
// by in-game day, newest first. The folded scene says what came of it —
// deals, plans changed, feelings that moved; unfolded, the whole
// conversation and what each side will remember. (Conversations still
// going are in "Talking now" above.)

// "insert VISIT at Smithy with Edmund 06:00-07:00 day 3" -> "+ VISIT Smithy
// with Edmund, day 3 06:00–07:00". Labels come from schedule.apply_ops.
function planEdit(label) {
  const m = label.match(/^insert (\w+) at (\w+)(?: with (\w+))? (\d\d:\d\d)-(\d\d:\d\d) day (\d+)$/);
  if (m) {
    const [, what, where, who, from, to, day] = m;
    return `+ ${what} ${where}${who ? ` with ${who}` : ""}, day ${day} ${from}–${to}`;
  }
  if (label.startsWith("cancel")) return "cancelled a block";
  if (label.startsWith("move")) return "moved a block";
  return label;
}

function signed(n) {
  return n > 0 ? `+${n}` : `−${Math.abs(n)}`;
}

function Scene({ c, colors }) {
  const changes = c.replans.flatMap((r) => r.applied.map((a) => ({ who: r.who, text: planEdit(a) })));
  const feelings = c.replans.filter((r) => r.affinity);
  const memories = c.replans.filter((r) => r.memory);
  return (
    <details className="scene">
      <summary>
        <span className="scene-head">
          <span className="scene-time">{c.started.replace(/^Day \d+ /, "")}</span>
          <strong>
            <span style={{ color: colors[c.a] }}>{c.a}</span> ↔{" "}
            <span style={{ color: colors[c.b] }}>{c.b}</span>
          </strong>
          <span className="scene-meta">{c.place} · {REASON[c.reason] ?? c.reason}</span>
        </span>
        {(c.deals.length > 0 || changes.length > 0 || feelings.length > 0) && (
          <span className="talk-chips">
            {c.deals.map((d, i) => (
              <span key={`d${i}`} className="chip deal">
                {d.buyer} bought {d.quantity} {d.item.replace("_", " ")} · {amount(d.price, d.quantity)}
              </span>
            ))}
            {changes.map((ch, i) => (
              <span key={`p${i}`} className="chip plan">{ch.who}: {ch.text}</span>
            ))}
            {feelings.map((r) => {
              const other = r.who === c.a ? c.b : c.a;
              return (
                <span key={`f${r.who}`} className={`chip ${r.affinity > 0 ? "accept" : "reject"}`}>
                  {r.who} → {other} {signed(r.affinity)}
                </span>
              );
            })}
          </span>
        )}
      </summary>
      <ol className="talk-lines">
        {c.lines.map((line, i) => (
          <Line key={i} line={line} colors={colors}
                deal={line.response === "accept" ? c.deals.find((d) => d.tick === line.tick) : null} />
        ))}
      </ol>
      {memories.length > 0 && (
        <ul className="scene-memories">
          {memories.map((r) => (
            <li key={r.who}><strong>{r.who}</strong> will remember: “{r.memory}”</li>
          ))}
        </ul>
      )}
      <p className="scene-end">
        {c.started} – {c.ended?.replace(/^Day \d+ /, "")} · {ENDED[c.end_reason] ?? c.end_reason}
      </p>
    </details>
  );
}

export default function SceneLog({ conversations, colors, onMore, hasMore }) {
  const ended = conversations.filter((c) => c.status === "ended");
  const days = [];
  for (const c of ended) {
    const day = c.started.match(/^Day (\d+)/)?.[1] ?? "?";
    if (days.at(-1)?.day !== day) days.push({ day, scenes: [] });
    days.at(-1).scenes.push(c);
  }
  return (
    <section className="scene-log">
      <h2>Village log</h2>
      {ended.length === 0 && <p className="empty">Nothing has happened yet…</p>}
      {days.map(({ day, scenes }) => (
        <div key={day} className="scene-day">
          <h3>Day {day}</h3>
          {scenes.map((c) => <Scene key={c.id} c={c} colors={colors} />)}
        </div>
      ))}
      {hasMore && (
        <button type="button" className="scene-more" onClick={onMore}>Show older scenes</button>
      )}
    </section>
  );
}
