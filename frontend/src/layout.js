// Where each villager is drawn on the map, in tile units (centre of the
// tile). The simulation gives everyone inside a building a standing spot
// of their own (backend/world/map.py), so the drawn position is the
// server's x/y — this only decides which side of the dot the name tag
// goes on.
//
// Shared by the villager layer (dots, name tags) and the speech bubbles,
// so a bubble always sits over its speaker.

// Two villagers can still share a tile — walking out of the Inn side by
// side, or a seventh guest when the spots run out. They are nudged this
// far apart sideways (and alternate tags above/below) so both show.
const SHARED_NUDGE = 0.35;

export function displayPositions(villagers, buildings = []) {
  const sharing = new Map();   // "x,y" -> villagers on that tile, by name
  for (const v of [...villagers].sort((a, b) => a.name.localeCompare(b.name))) {
    const key = `${v.x},${v.y}`;
    sharing.set(key, [...(sharing.get(key) ?? []), v.id]);
  }
  const out = new Map();
  for (const v of villagers) {
    // Inside, the row below the middle tile carries its tag below the dot,
    // so a full Inn doesn't stack the tags of two rows onto one line.
    const b = buildings.find((b) => b.x <= v.x && v.x < b.x + b.width
                                   && b.y <= v.y && v.y < b.y + b.height);
    let labelBelow = Boolean(b) && v.y > b.y + Math.floor(b.height / 2);
    let dx = 0;
    const group = sharing.get(`${v.x},${v.y}`);
    if (group.length > 1) {
      const i = group.indexOf(v.id);
      dx = (i - (group.length - 1) / 2) * SHARED_NUDGE * 2;
      labelBelow = i % 2 === 1;
    }
    out.set(v.id, { x: v.x + 0.5 + dx, y: v.y + 0.5, labelBelow });
  }
  return out;
}
