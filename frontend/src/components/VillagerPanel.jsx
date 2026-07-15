import { formatCopper } from "../currency.js";

const STATUS_ICON = {
  idle: "🧍", moving: "🚶", working: "🔨", talking: "💬",
  trading: "🪙", resting: "💤", observing: "👀",
};

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
