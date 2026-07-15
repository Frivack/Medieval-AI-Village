import { tickToClock } from "../currency.js";

export default function ControlBar({ time, busy, autoRun, onAdvance, onToggleAuto }) {
  return (
    <header className="control-bar">
      <h1>Medieval AI Village</h1>
      <div className="clock">{time ? tickToClock(time.tick) : "—"}</div>
      <div className="controls">
        <button disabled={busy} onClick={() => onAdvance(1)}>+5 min</button>
        <button disabled={busy} onClick={() => onAdvance(12)}>+1 hour</button>
        <button disabled={busy} onClick={() => onAdvance(288)}>+1 day</button>
        <button className={autoRun ? "auto on" : "auto"} onClick={onToggleAuto}>
          {autoRun ? "⏸ Pause" : "▶ Auto"}
        </button>
      </div>
    </header>
  );
}
