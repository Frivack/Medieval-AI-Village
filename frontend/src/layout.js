// Where each villager is drawn on the map, in tile units (centre of the
// spot). In the simulation everyone inside a building stands on the same
// interior tile, so four villagers at the Inn would be one blob; on
// screen they spread out around that tile instead. Presentation only —
// the backend's positions and pathfinding are untouched.
//
// Shared by the map canvas (circles, name labels) and the speech bubbles,
// so a bubble always sits over its speaker.

// Spots around the shared tile, in the order villagers fill them (sorted
// by name, so each keeps the same place while the group stays the same).
// Two tiles apart sideways leaves room for the name labels.
const SPOTS = [[-2, -1], [2, -1], [-2, 1], [2, 1], [0, -1], [0, 1]];

export function displayPositions(villagers, buildings = []) {
  const groups = new Map();
  for (const v of villagers) {
    const key = `${v.x},${v.y}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(v);
  }
  const out = new Map();
  for (const group of groups.values()) {
    if (group.length === 1) {
      const v = group[0];
      out.set(v.id, { x: v.x + 0.5, y: v.y + 0.5, labelBelow: false });
      continue;
    }
    const b = buildings.find((b) => b.x <= group[0].x && group[0].x < b.x + b.width
                                   && b.y <= group[0].y && group[0].y < b.y + b.height);
    [...group].sort((a, c) => a.name.localeCompare(c.name)).forEach((v, i) => {
      const [dx, dy] = SPOTS[i % SPOTS.length];
      let x = v.x + dx, y = v.y + dy;
      if (b) {   // stay on the floor, inside the walls
        x = Math.min(Math.max(x, b.x + 1), b.x + b.width - 2);
        y = Math.min(Math.max(y, b.y + 1), b.y + b.height - 2);
      }
      out.set(v.id, { x: x + 0.5, y: y + 0.5, labelBelow: dy > 0 });
    });
  }
  return out;
}
