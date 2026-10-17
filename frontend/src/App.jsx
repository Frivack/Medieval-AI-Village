import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { advanceTicks, fetchConversations, fetchMap, fetchStatus, fetchTime,
         fetchVillager, fetchVillagers } from "./api.js";
import ControlBar from "./components/ControlBar.jsx";
import ConversationPanel from "./components/ConversationPanel.jsx";
import MapView from "./components/MapView.jsx";
import SceneLog from "./components/SceneLog.jsx";
import { JOB_COLORS } from "./colors.js";
import VillagerDetail from "./components/VillagerDetail.jsx";
import VillagerPanel from "./components/VillagerPanel.jsx";

const POLL_MS = 2000;      // background refresh (catches ticks from the server loop / other clients)
const AUTO_TICK_MS = 700;  // pace of the ▶ Auto mode
const SCENES_PAGE = 20;    // conversations fetched at first and per "Show older scenes"

export default function App() {
  const [map, setMap] = useState(null);
  const [status, setStatus] = useState(null); // how this server advances time
  const [villagers, setVillagers] = useState([]);
  const [time, setTime] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [busy, setBusy] = useState(false);
  const [autoRun, setAutoRun] = useState(false);
  const [error, setError] = useState(null);
  const ticking = useRef(false); // prevents overlapping /tick requests
  // How many conversations to fetch: one list feeds the bubbles, "Talking
  // now" and the scene log; "Show older scenes" raises it.
  const sceneLimit = useRef(SCENES_PAGE);
  // The villager whose detail view is open (a card or their dot on the map
  // was clicked), and their full record, refreshed with everything else.
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const selectedRef = useRef(null);

  // The world only changes on a tick (once a minute on the live server), so
  // the poll asks /time first and fetches the rest only when the tick moved.
  // force: the view wants different data now (detail opened, older scenes).
  const lastTick = useRef(null);
  const refresh = useCallback(async (force = false) => {
    try {
      const t = await fetchTime();
      if (!force && t.tick === lastTick.current) {
        setError(null);
        return;
      }
      const id = selectedRef.current;
      const [v, c, d] = await Promise.all([
        fetchVillagers(), fetchConversations(sceneLimit.current),
        id ? fetchVillager(id) : null,
      ]);
      lastTick.current = t.tick;
      setVillagers(v);
      setTime(t);
      setConversations(c);
      if (id && selectedRef.current === id) setDetail(d);   // ignore if closed meanwhile
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
      await refresh(true);
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

  const select = useCallback((id) => {
    selectedRef.current = id;
    setSelectedId(id);
    setDetail(null);
    if (id) refresh(true);
  }, [refresh]);
  const closeDetail = useCallback(() => select(null), [select]);

  const showOlderScenes = useCallback(() => {
    sceneLimit.current += SCENES_PAGE;
    refresh(true);
  }, [refresh]);

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
          <MapView map={map} villagers={villagers} bubbles={bubbles}
                   selectedId={selectedId} onSelect={select} />
        </div>
        <aside className="sidebar">
          <ConversationPanel conversations={conversations} colors={colorByName} />
          {selectedId
            ? <VillagerDetail detail={detail} colors={colorByName}
                              minutesPerTick={status?.minutes_per_tick} onBack={closeDetail} />
            : <VillagerPanel villagers={villagers} onSelect={select} />}
          <SceneLog conversations={conversations} colors={colorByName}
                    onMore={showOlderScenes}
                    hasMore={conversations.length >= sceneLimit.current} />
        </aside>
      </main>
    </div>
  );
}
