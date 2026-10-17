// Where each villager is drawn on the map, in tile units (centre of the
// tile). The simulation gives everyone inside a building a standing spot
// of their own (backend/world/map.py), so the drawn position is the
// server's x/y — this only decides which side of the dot the name tag
// goes on.
//
// Shared by the villager layer (dots, name tags) and the speech bubbles,
// so a bubble always sits over its speaker.

export function displayPositions(villagers, buildings = []) {
  const out = new Map();
  for (const v of villagers) {
    // Inside, the row below the middle tile carries its tag below the dot,
    // so a full Inn doesn't stack the tags of two rows onto one line.
    const b = buildings.find((b) => b.x <= v.x && v.x < b.x + b.width
                                   && b.y <= v.y && v.y < b.y + b.height);
    const labelBelow = Boolean(b) && v.y > b.y + Math.floor(b.height / 2);
    out.set(v.id, { x: v.x + 0.5, y: v.y + 0.5, labelBelow });
  }
  return out;
}
