import { formatCopper } from "../currency.js";

const STATUS_ICON = {
  idle: "🧍", moving: "🚶", working: "🔨", talking: "💬",
  trading: "🪙", resting: "💤", observing: "👀",
  socializing: "🍺", visiting: "🚪", eating: "🍞",
};

// A 0-100 gauge. `bad` marks the end that means trouble: hunger is bad
// when high, a tool's condition when low. Shared with the detail view.
export function Gauge({ label, value, bad }) {
  const v = Math.max(0, Math.min(100, value));
  const alarm = bad === "high" ? v >= 50 : v <= 25;
  return (
    <div className="gauge" title={`${label} ${Math.round(v)}/100`}>
      <span className="gauge-label">{label}</span>
      <span className="gauge-track">
        <span className={alarm ? "gauge-fill alarm" : "gauge-fill"} style={{ width: `${v}%` }} />
      </span>
    </div>
  );
}

// "WORK @ Smithy until Day 1 18:00" — the schedule block in force, which
// is what the villager is doing or walking towards.
function activityText(a) {
  const who = a.with ? ` with ${a.with}` : "";
  return `${a.do} @ ${a.at}${who} until ${a.until}`;
}

// Each card opens that villager's detail view (click, Enter or Space).
export default function VillagerPanel({ villagers, onSelect }) {
  return (
    <section className="villager-panel">
      {villagers.map((v) => (
        <article
          className="villager-card" key={v.id}
          role="button" tabIndex={0} aria-label={`${v.name}, ${v.job}: open details`}
          onClick={() => onSelect(v.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(v.id); }
          }}
        >
          <div className="card-head">
            <strong>{v.name}</strong>
            <span className="job">{v.job}</span>
          </div>
          <div className="card-row">
            <span>{STATUS_ICON[v.status] ?? "❓"} {v.status}</span>
            <span className="loc">@ {v.location}</span>
          </div>
          {v.activity && (
            <div className="activity" title={v.activity.why ?? ""}>
              {activityText(v.activity)}
            </div>
          )}
          <div className="card-row">
            <span className="wealth">{formatCopper(v.wealth)}</span>
          </div>
          {v.needs && (
            <div className="gauges">
              <Gauge label="hunger" value={v.needs.hunger} bad="high" />
              {"tool" in v.needs && <Gauge label="tool" value={v.needs.tool} bad="low" />}
            </div>
          )}
          <div className="inventory">
            {Object.entries(v.inventory ?? {}).map(([item, n]) => (
              <span className="item" key={item}>{item} ×{n}</span>
            ))}
          </div>
        </article>
      ))}
    </section>
  );
}
