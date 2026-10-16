import { formatClock } from "../clock.js";

// Manual time steps in in-game minutes; converted to ticks with the
// backend's minutes_per_tick so the buttons survive time-scale changes.
const STEPS = [["+10 min", 10], ["+1 hour", 60], ["+1 day", 24 * 60]];

// status comes from GET /status. On the public server time is driven by the
// backend itself (auto_tick) and manual ticking is disabled — every tick
// costs LLM calls — so visitors get a LIVE badge instead of the buttons.
export default function ControlBar({ time, status, busy, autoRun, onAdvance, onToggleAuto }) {
  return (
    <header className="control-bar">
      <h1>Medieval AI Village</h1>
      <div className="clock">{time ? formatClock(time) : "—"}</div>
      {status?.auto_tick && (
        <div
          className="live"
          title={`Time runs on the server: ${status.minutes_per_tick} in-game minute(s) every ${status.tick_interval_seconds} s`}
        >
          <span className="live-dot" />LIVE
        </div>
      )}
      {status?.manual_tick && (
        <div className="controls">
          {STEPS.map(([label, minutes]) => (
            <button
              key={label}
              disabled={busy}
              onClick={() => onAdvance(Math.max(1, Math.round(minutes / status.minutes_per_tick)))}
            >
              {label}
            </button>
          ))}
          <button className={autoRun ? "auto on" : "auto"} onClick={onToggleAuto}>
            {autoRun ? "⏸ Pause" : "▶ Auto"}
          </button>
        </div>
      )}
    </header>
  );
}
