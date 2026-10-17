// Day and night over the terrain: a tint that follows the in-game clock
// (dark blue at night, orange at dawn and dusk, clear by day), and a warm
// glow in the windows of every building where someone is awake. It sits
// between the terrain canvas and the villagers, so names and speech
// bubbles stay bright at night.

// [minute of the day, [r, g, b, alpha]]; the tint is interpolated between
// these, wrapping round midnight.
const SKY = [
  [0,         [12, 20, 60, 0.45]],
  [4 * 60 + 30, [12, 20, 60, 0.45]],
  [6 * 60,    [255, 150, 80, 0.15]],   // sunrise
  [7 * 60,    [255, 200, 150, 0]],
  [17 * 60 + 30, [255, 200, 150, 0]],
  [18 * 60 + 30, [255, 120, 60, 0.18]], // sunset
  [19 * 60 + 30, [40, 30, 90, 0.32]],
  [21 * 60,   [12, 20, 60, 0.45]],
  [24 * 60,   [12, 20, 60, 0.45]],
];
const NIGHT_ALPHA = 0.45;

export function skyAt(minuteOfDay) {
  const i = SKY.findIndex(([m]) => m > minuteOfDay);
  const [m0, c0] = SKY[i - 1];
  const [m1, c1] = SKY[i];
  const t = (minuteOfDay - m0) / (m1 - m0);
  return c0.map((v, k) => v + (c1[k] - v) * t);
}

export default function DayNight({ map, time, villagers }) {
  if (!time) return null;
  const [r, g, b, a] = skyAt(time.hour * 60 + time.minute);
  const dark = a / NIGHT_ALPHA;            // 0 by day .. 1 at night
  const awake = new Set(villagers.filter((v) => v.status !== "resting").map((v) => v.location));
  const pct = (n, of) => `${(n / of) * 100}%`;
  return (
    <div className="sky-layer" aria-hidden="true"
         style={{ background: `rgba(${r | 0}, ${g | 0}, ${b | 0}, ${a.toFixed(3)})` }}>
      {dark > 0.3 && map.buildings.filter((bd) => awake.has(bd.name)).map((bd) => (
        <span key={bd.name} className="window-glow" style={{
          left: pct(bd.x - 1, map.width), top: pct(bd.y - 1, map.height),
          width: pct(bd.width + 2, map.width), height: pct(bd.height + 2, map.height),
          opacity: Math.min(1, dark).toFixed(2),
        }} />
      ))}
    </div>
  );
}
