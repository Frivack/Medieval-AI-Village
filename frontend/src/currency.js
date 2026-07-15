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

// Ticks -> in-game clock (mirrors backend: 1 tick = 5 minutes).
export function tickToClock(tick) {
  const TICKS_PER_HOUR = 12;
  const TICKS_PER_DAY = 288;
  const dayTick = ((tick % TICKS_PER_DAY) + TICKS_PER_DAY) % TICKS_PER_DAY;
  const day = Math.floor(tick / TICKS_PER_DAY) + 1;
  const hour = Math.floor(dayTick / TICKS_PER_HOUR);
  const minute = (dayTick % TICKS_PER_HOUR) * 5;
  const pad = (n) => String(n).padStart(2, "0");
  return `Day ${day} ${pad(hour)}:${pad(minute)}`;
}
