import { useEffect, useState } from "react";
import { formatCopper } from "../currency.js";
import { Gauge } from "./VillagerPanel.jsx";
import { signed, withoutDay } from "../format.js";

// One villager in full (GET /villagers/{id}): what their day looks like —
// with the blocks the AI planned and why — how they stand, how they feel
// about the others and how the others feel back, and what they remember.
// Replaces the villager cards in the sidebar while open.

const MINUTES_PER_DAY = 24 * 60;
const ACTIVITIES = ["WORK", "SOCIAL", "SLEEP", "VISIT"];
const FEELS = { "close friend": "close friend", like: "likes", neutral: "neutral",
                wary: "wary of", dislike: "dislikes" };
const MEMORIES_SHOWN = 12;


// A 24-hour bar for one in-game day. Blocks are clipped to the day; the
// part of today that has passed is shaded (finished blocks aren't kept).
function DayBar({ label, start, perDay, now, blocks }) {
  const end = start + perDay;
  const pct = (t) => ((Math.min(Math.max(t, start), end) - start) / perDay) * 100;
  const shown = blocks.filter((b) => b.end > start && b.start < end);
  const nowIn = now >= start && now < end;
  return (
    <div className="day-bar">
      <span className="day-bar-label">{label}</span>
      <div className="day-bar-track">
        {nowIn && <div className="day-bar-past" style={{ width: `${pct(now)}%` }} />}
        {shown.map((b) => (
          <div
            key={b.start}
            className={`seg seg-${b.do.toLowerCase()}${b.ai ? " ai" : ""}${b.current ? " current" : ""}`}
            style={{ left: `${pct(b.start)}%`, width: `${pct(b.end) - pct(b.start)}%` }}
            title={`${b.from}–${withoutDay(b.to)} ${b.do} @ ${b.at}${b.with ? ` with ${b.with}` : ""}${b.why ? ` — ${b.why}` : ""}`}
          />
        ))}
        {nowIn && <div className="day-bar-now" style={{ left: `${pct(now)}%` }} />}
      </div>
      <div className="day-bar-hours" aria-hidden="true">
        <span>0</span><span>6</span><span>12</span><span>18</span><span>24</span>
      </div>
    </div>
  );
}

// −30..30 as a bar from the middle: right and green when warm, left and
// red when cold.
function AffinityBar({ value }) {
  const half = (Math.min(Math.abs(value), 30) / 30) * 50;
  return (
    <span className="aff-track" aria-hidden="true">
      <span className={`aff-fill ${value >= 0 ? "warm" : "cold"}`}
            style={value >= 0 ? { left: "50%", width: `${half}%` } : { right: "50%", width: `${half}%` }} />
    </span>
  );
}

export default function VillagerDetail({ detail, colors, minutesPerTick, onBack }) {
  const [allMemories, setAllMemories] = useState(false);
  // Esc goes back to all villagers.
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onBack(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBack]);

  if (!detail) return <section className="villager-detail"><p className="empty">Loading…</p></section>;
  const d = detail;
  const perDay = MINUTES_PER_DAY / (minutesPerTick || 1);
  const todayStart = Math.floor(d.now / perDay) * perDay;
  const day = Math.floor(d.now / perDay) + 1;
  const memories = allMemories ? d.memories : d.memories.slice(0, MEMORIES_SHOWN);

  return (
    <section className="villager-detail" aria-label={`${d.name}, details`}>
      <button type="button" className="detail-back" onClick={onBack}>← All villagers</button>

      <header className="detail-head">
        <h2 style={{ "--accent": colors[d.name] }}>{d.name}</h2>
        <span className="job">{d.job}, {d.age} · works at the {d.workplace}</span>
        <p className="detail-personality">{d.personality}</p>
        <p className="detail-now">{d.status} @ {d.location} · <span className="wealth">{formatCopper(d.wealth)}</span></p>
        <div className="gauges">
          <Gauge label="hunger" value={d.needs.hunger} bad="high" />
          {"tool" in d.needs && <Gauge label="tool" value={d.needs.tool} bad="low" />}
        </div>
        <div className="inventory">
          {Object.entries(d.inventory).map(([item, n]) => (
            <span className="item" key={item}>{item.replace("_", " ")} ×{n}</span>
          ))}
        </div>
      </header>

      <h3>Schedule</h3>
      <DayBar label={`Day ${day}`} start={todayStart} perDay={perDay} now={d.now} blocks={d.schedule} />
      <DayBar label={`Day ${day + 1}`} start={todayStart + perDay} perDay={perDay} now={d.now} blocks={d.schedule} />
      <div className="seg-legend" aria-hidden="true">
        {ACTIVITIES.map((a) => <span key={a}><i className={`seg-${a.toLowerCase()}`} />{a.toLowerCase()}</span>)}
        <span><i className="legend-ai" />planned by the villager</span>
      </div>
      <ol className="detail-blocks">
        {d.schedule.map((b) => (
          <li key={b.start} className={`${b.ai ? "ai" : ""}${b.current ? " current" : ""}`}>
            <span className="block-time">{b.from}–{withoutDay(b.to)}</span>
            <span>
              {b.do} @ {b.at}{b.with ? ` with ${b.with}` : ""}
              {b.current && <span className="chip">now</span>}
              {b.ai && <span className="chip plan">planned</span>}
            </span>
            {b.why && <span className="block-why">{b.why}</span>}
          </li>
        ))}
      </ol>

      <h3>Feelings</h3>
      <ul className="detail-relations">
        {d.relationships.map((r) => (
          <li key={r.id}>
            <span className="rel-name" style={{ "--accent": colors[r.name] }}>{r.name}</span>
            <AffinityBar value={r.affinity} />
            <span className="rel-text">
              {FEELS[r.level]} ({signed(r.affinity)}) · they: {FEELS[r.their_level]} ({signed(r.their_affinity)})
              {r.last_talk && <span className="muted"> · last talked {r.last_talk}</span>}
            </span>
          </li>
        ))}
      </ul>

      <h3>Memories</h3>
      {d.memories.length === 0 && <p className="empty">Nothing yet.</p>}
      <ol className="detail-memories">
        {memories.map((m, i) => (
          <li key={`${m.tick}-${i}`}>
            <span className="mem-meta">
              <span className="mem-importance" title={`importance ${m.importance} of 3`}>
                {"●".repeat(m.importance)}{"○".repeat(3 - m.importance)}
              </span>
              {m.time}
            </span>
            <span>{m.text}</span>
            {m.told.length > 0 && <span className="muted mem-told">told {m.told.join(", ")}</span>}
          </li>
        ))}
      </ol>
      {d.memories.length > MEMORIES_SHOWN && (
        <button type="button" className="scene-more" onClick={() => setAllMemories((a) => !a)}>
          {allMemories ? "Show fewer" : `Show all ${d.memories.length}`}
        </button>
      )}
    </section>
  );
}
