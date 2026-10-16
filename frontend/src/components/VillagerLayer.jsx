import { JOB_COLORS } from "../colors.js";

// Villagers, their name tags and the building names, as HTML over the
// terrain canvas. Positions are in percent of the map and sizes in cqw
// (1cqw = one tile), so this layer scales with the map like the tiles do
// but stays sharp at any zoom. Where each villager stands on screen comes
// from layout.js (people sharing a tile spread out around it).

export default function VillagerLayer({ map, villagers, positions }) {
  const at = (x, y) => ({ left: `${(x / map.width) * 100}%`, top: `${(y / map.height) * 100}%` });
  return (
    <div className="people-layer">
      {map.buildings.map((b) => (
        <span key={b.name} className="building-label" style={at(b.x + b.width / 2, b.y - 0.7)}>
          {b.name}
        </span>
      ))}
      {villagers.map((v) => {
        const pos = positions.get(v.id);
        return (
          <div key={v.id} className="villager" style={at(pos.x, pos.y)}>
            <span className="villager-dot" style={{ background: JOB_COLORS[v.job] ?? "#fff" }} />
            {/* Above the head, or below for the lower row of a group, so a
                crowd at the Inn doesn't stack four tags on top of each other. */}
            <span className={`villager-name${pos.labelBelow ? " below" : ""}`}>{v.name}</span>
          </div>
        );
      })}
    </div>
  );
}
