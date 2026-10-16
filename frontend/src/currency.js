// Mirrors backend/utils/currency.py: 1 gold = 20 silver = 200 copper.
const COPPER_PER_SILVER = 10;
const COPPER_PER_GOLD = 200;

export function formatCopper(copper) {
  const gold = Math.floor(copper / COPPER_PER_GOLD);
  const rem = copper % COPPER_PER_GOLD;
  const silver = Math.floor(rem / COPPER_PER_SILVER);
  const c = rem % COPPER_PER_SILVER;
  const parts = [];
  if (gold > 0) parts.push(`${gold}g`);
  if (silver > 0) parts.push(`${silver}s`);
  if (c > 0) parts.push(`${c}c`);
  return parts.length ? parts.join(" ") : "0c";
}
