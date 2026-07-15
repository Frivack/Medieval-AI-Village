import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { advanceTicks, fetchHistory, fetchMap, fetchTime, fetchVillagers } from "./api.js";
import ControlBar from "./components/ControlBar.jsx";
import HistoryFeed from "./components/HistoryFeed.jsx";
import MapCanvas from "./components/MapCanvas.jsx";
import VillagerPanel from "./components/VillagerPanel.jsx";

const POLL_MS = 2000;      // background refresh (catches ticks from other clients)
const AUTO_TICK_MS = 700;  // pace of the ▶ Auto mode

export default function App() {
  const [map, setMap] = useState(null);
  const [villagers, setVillagers] = useState([]);
  const [time, setTime] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [autoRun, setAutoRun] = useState(false);
  const [error, setError] = useState(null);
  const ticking = useRef(false); // prevents overlapping /tick requests

  const refresh = useCallback(async () => {
    try {
      const [v, t, h] = await Promise.all([
        fetchVillagers(), fetchTime(), fetchHistory(60),
      ]);
      setVillagers(v);
      setTime(t);
      setHistory(h);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  // Static map: fetched once.
  useEffect(() => {
    fetchMap().then(setMap).catch((e) => setError(String(e)));
    refresh();
  }, [refresh]);

  // Slow background poll.
  useEffect(() => {
    const id = setInterval(() => { if (!ticking.current) refresh(); }, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const onAdvance = useCallback(async (count) => {
    if (ticking.current) return;
    ticking.current = true;
    setBusy(true);
    try {
      await advanceTicks(count);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      ticking.current = false;
      setBusy(false);
    }
  }, [refresh]);

  // Auto mode: one tick every AUTO_TICK_MS.
  useEffect(() => {
    if (!autoRun) return;
    const id = setInterval(() => { onAdvance(1); }, AUTO_TICK_MS);
    return () => clearInterval(id);
  }, [autoRun, onAdvance]);

  const nameById = useMemo(
    () => Object.fromEntries(villagers.map((v) => [v.id, v.name])),
    [villagers]
  );

  return (
    <div className="app">
      <ControlBar
        time={time}
        busy={busy}
        autoRun={autoRun}
        onAdvance={onAdvance}
        onToggleAuto={() => setAutoRun((a) => !a)}
      />
      {error && <div className="error-banner">{error}</div>}
      <main className="layout">
        <div className="map-wrap">
          <MapCanvas map={map} villagers={villagers} />
        </div>
        <aside className="sidebar">
          <VillagerPanel villagers={villagers} />
          <HistoryFeed history={history} nameById={nameById} />
        </aside>
      </main>
    </div>
  );
}
