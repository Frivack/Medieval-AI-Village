// In-game clock formatting. The time scale (minutes_per_tick) comes from
// GET /status, so it's never hard-coded here — the backend changed it from
// 5 minutes to 1 minute per tick once already.
const MINUTES_PER_DAY = 24 * 60;
const pad = (n) => String(n).padStart(2, "0");

export function formatClock({ day, hour, minute }) {
  return `Day ${day} ${pad(hour)}:${pad(minute)}`;
}

export function tickToClock(tick, minutesPerTick) {
  if (!minutesPerTick) return `tick ${tick}`; // /status not loaded yet
  const minutes = tick * minutesPerTick;
  const inDay = ((minutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY;
  return formatClock({
    day: Math.floor(minutes / MINUTES_PER_DAY) + 1,
    hour: Math.floor(inDay / 60),
    minute: inDay % 60,
  });
}
