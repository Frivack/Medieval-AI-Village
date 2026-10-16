import { formatCopper } from "../currency.js";

const STATUS_ICON = {
  idle: "🧍", moving: "🚶", working: "🔨", talking: "💬",
  trading: "🪙", resting: "💤", observing: "👀",
  socializing: "🍺", visiting: "🚪",
};

// "WORK @ Smithy until Day 1 18:00" — the schedule block in force, which
// is what the villager is doing or walking towards.
function activityText(a) {
  const who = a.with ? ` with ${a.with}` : "";
  return `${a.do} @ ${a.at}${who} until ${a.until}`;
}

export default function VillagerPanel({ villagers }) {
  return (
    <section className="villager-panel">
      {villagers.map((v) => (
        <article className="villager-card" key={v.id}>
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
