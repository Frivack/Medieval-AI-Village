import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { advanceTicks, fetchConversations, fetchHistory, fetchMap, fetchStatus, fetchTime,
         fetchVillagers } from "./api.js";
import ControlBar from "./components/ControlBar.jsx";
import ConversationPanel from "./components/ConversationPanel.jsx";
import HistoryFeed from "./components/HistoryFeed.jsx";
import MapView from "./components/MapView.jsx";
import { JOB_COLORS } from "./colors.js";
import VillagerPanel from "./components/VillagerPanel.jsx";

const POLL_MS = 2000;      // background refresh (catches ticks from the server loop / other clients)
const AUTO_TICK_MS = 700;  // pace of the ▶ Auto mode

export default function App() {
  const [map, setMap] = useState(null);
  const [status, setStatus] = useState(null); // how this server advances time
  const [villagers, setVillagers] = useState([]);
  const [time, setTime] = useState(null);
  const [history, setHistory] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [autoRun, setAutoRun] = useState(false);
  const [error, setError] = useState(null);
  const ticking = useRef(false); // prevents overlapping /tick requests

  const refresh = useCallback(async () => {
    try {
      const [v, t, h, c] = await Promise.all([
        fetchVillagers(), fetchTime(), fetchHistory(60), fetchConversations(10),
      ]);
      setVillagers(v);
      setTime(t);
      setHistory(h);
      setConversations(c);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  // Static map and server mode: fetched once.
  useEffect(() => {
    fetchMap().then(setMap).catch((e) => setError(String(e)));
    fetchStatus().then(setStatus).catch((e) => setError(String(e)));
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

  const colorByName = useMemo(
    () => Object.fromEntries(villagers.map((v) => [v.name, JOB_COLORS[v.job]])),
    [villagers]
  );

  // A bubble for every line said on the current tick — the newest line of
  // each conversation, active or just ended (a goodbye still shows).
  const bubbles = useMemo(() => {
    if (!time) return [];
    const byName = Object.fromEntries(villagers.map((v) => [v.name, v]));
    return conversations.flatMap((c) => {
      const line = c.lines?.at(-1);
      const speaker = line && byName[line.speaker];
      if (!speaker || line.tick !== time.tick) return [];
      return [{ key: `${c.id}:${line.tick}`, speakerId: speaker.id, line,
                color: JOB_COLORS[speaker.job] }];
    });
  }, [conversations, time, villagers]);

  return (
    <div className="app">
      <ControlBar
        time={time}
        status={status}
        busy={busy}
        autoRun={autoRun}
        onAdvance={onAdvance}
        onToggleAuto={() => setAutoRun((a) => !a)}
      />
      {error && <div className="error-banner">{error}</div>}
      <main className="layout">
        <div className="map-wrap">
          <MapView map={map} villagers={villagers} bubbles={bubbles} />
        </div>
        <aside className="sidebar">
          <ConversationPanel conversations={conversations} colors={colorByName} />
          <VillagerPanel villagers={villagers} />
          <HistoryFeed history={history} nameById={nameById}
                       minutesPerTick={status?.minutes_per_tick} />
        </aside>
      </main>
    </div>
  );
}
