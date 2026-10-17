import { useEffect, useRef } from "react";
import { JOB_COLORS } from "../colors.js";

// Villagers, their name tags and the building names, as HTML over the
// terrain canvas. Positions are in percent of the map and sizes in cqw
// (1cqw = one tile), so this layer scales with the map like the tiles do
// but stays sharp at any zoom. Where each villager stands comes from the
// server (each has a spot of their own inside a building); layout.js
// turns it into map units and picks the tag's side.
//
// Walking: the simulation moves one tile per tick, so a one-tile move
// glides over `stepSeconds` (one tick) at a steady pace. When the next
// step arrives mid-glide the browser carries on from where the dot is, so
// a walk looks continuous. A longer jump ("+1 hour", the first load)
// snaps — gliding across the map would show a path nobody walked.
const STEP_TILES = 1.5;  // a move up to this far counts as one step

// A villager's dot and tag carry data-villager: MapView reads it to open
// their details on a tap. The selected one gets a ring.
export default function VillagerLayer({ map, villagers, positions, selectedId, stepSeconds = 0.7 }) {
  const at = (x, y) => ({ left: `${(x / map.width) * 100}%`, top: `${(y / map.height) * 100}%` });
  // Where each villager was drawn last render, to tell a step from a jump.
  const drawn = useRef(new Map());
  useEffect(() => { drawn.current = positions; });
  return (
    <div className="people-layer">
      {map.buildings.map((b) => (
        <span key={b.name} className="building-label" style={at(b.x + b.width / 2, b.y - 0.7)}>
          {b.name}
        </span>
      ))}
      {villagers.map((v) => {
        const pos = positions.get(v.id);
        const last = drawn.current.get(v.id);
        const step = last && Math.hypot(pos.x - last.x, pos.y - last.y) <= STEP_TILES;
        const transition = step ? `left ${stepSeconds}s linear, top ${stepSeconds}s linear` : "none";
        return (
          <div key={v.id} className={`villager${v.id === selectedId ? " selected" : ""}`}
               style={{ ...at(pos.x, pos.y), transition }} data-villager={v.id}
               title={`${v.name} — click for details`}>
            <span className="villager-dot" style={{ background: JOB_COLORS[v.job] ?? "#fff" }} />
            {/* Above the head, or below for the lower row inside a building,
                so a crowd at the Inn doesn't stack four tags on one line. */}
            <span className={`villager-name${pos.labelBelow ? " below" : ""}`}>{v.name}</span>
          </div>
        );
      })}
    </div>
  );
}
