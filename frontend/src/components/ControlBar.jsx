import { tickToClock } from "../currency.js";

// status comes from GET /status. On the public server time is driven by the
// backend itself (auto_tick) and manual ticking is disabled — every tick
// costs LLM calls — so visitors get a LIVE badge instead of the buttons.
export default function ControlBar({ time, status, busy, autoRun, onAdvance, onToggleAuto }) {
  return (
    <header className="control-bar">
      <h1>Medieval AI Village</h1>
      <div className="clock">{time ? tickToClock(time.tick) : "—"}</div>
      {status?.auto_tick && (
        <div
          className="live"
          title={`Time runs on the server: 5 in-game minutes every ${status.tick_interval_seconds} s`}
        >
          <span className="live-dot" />LIVE
        </div>
      )}
      {status?.manual_tick && (
        <div className="controls">
          <button disabled={busy} onClick={() => onAdvance(1)}>+5 min</button>
          <button disabled={busy} onClick={() => onAdvance(12)}>+1 hour</button>
          <button disabled={busy} onClick={() => onAdvance(288)}>+1 day</button>
          <button className={autoRun ? "auto on" : "auto"} onClick={onToggleAuto}>
            {autoRun ? "⏸ Pause" : "▶ Auto"}
          </button>
        </div>
      )}
    </header>
  );
}
