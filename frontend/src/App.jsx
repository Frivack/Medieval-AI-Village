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
import { useMedia } from "./useMedia.js";

const POLL_MS = 2000;      // background refresh (catches ticks from the server loop / other clients)
const AUTO_TICK_MS = 700;  // pace of the ▶ Auto mode
const SCENES_PAGE = 20;    // conversations fetched at first and per "Show older scenes"
// Phones: the map is ~350 px wide, so it zooms further, and the sidebar
// becomes tabs under the map instead of one long column.
const PHONE = "(max-width: 600px)";
const TABS = [["talk", "Talking now"], ["villagers", "Villagers"], ["log", "Village log"]];

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
  const phone = useMedia(PHONE);
  const [tab, setTab] = useState("talk");   // phones only
  const sidebarRef = useRef(null);

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
    if (id) {
      setTab("villagers");
      refresh(true);
    }
  }, [refresh]);

  // A villager opened from the map: bring the details into view when they
  // open off-screen — below the map in the one-column layout. On phones,
  // scroll to the tabs so it's clear which tab is showing.
  useEffect(() => {
    if (!selectedId) return;
    const target = phone ? sidebarRef.current : document.querySelector(".villager-detail");
    if (!target) return;
    const top = target.getBoundingClientRect().top;
    if (top >= 0 && top < window.innerHeight / 2) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ block: "start", behavior: still ? "auto" : "smooth" });
  }, [selectedId, phone]);
  const closeDetail = useCallback(() => select(null), [select]);

  const showOlderScenes = useCallback(() => {
    sceneLimit.current += SCENES_PAGE;
    refresh(true);
  }, [refresh]);

  // How long a one-tile step takes on screen: the server's tick interval
  // when it ticks by itself (60 s live — a walk at real-time speed), about
  // one ▶ Auto tick otherwise.
  const stepSeconds = status?.auto_tick ? status.tick_interval_seconds : AUTO_TICK_MS / 1000;

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

  const talking = conversations.filter((c) => c.status === "active").length;

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
                   selectedId={selectedId} onSelect={select} stepSeconds={stepSeconds}
                   time={time} maxZoom={phone ? 6 : 4} />
        </div>
        <aside className="sidebar" ref={sidebarRef}>
          {phone && (
            <div className="sidebar-tabs" role="tablist" aria-label="Village panels">
              {TABS.map(([id, label]) => (
                <button key={id} type="button" role="tab" id={`tab-${id}`}
                        aria-selected={tab === id} aria-controls={`panel-${id}`}
                        className={tab === id ? "on" : ""} onClick={() => setTab(id)}>
                  {label}
                  {id === "talk" && talking > 0 && <span className="tab-count">{talking}</span>}
                </button>
              ))}
            </div>
          )}
          <Panel id="talk" phone={phone} tab={tab}>
            <ConversationPanel conversations={conversations} colors={colorByName} />
          </Panel>
          <Panel id="villagers" phone={phone} tab={tab}>
            {selectedId
              ? <VillagerDetail detail={detail} colors={colorByName}
                                minutesPerTick={status?.minutes_per_tick} onBack={closeDetail} />
              : <VillagerPanel villagers={villagers} onSelect={select} />}
          </Panel>
          <Panel id="log" phone={phone} tab={tab}>
            <SceneLog conversations={conversations} colors={colorByName}
                      onMore={showOlderScenes}
                      hasMore={conversations.length >= sceneLimit.current} />
          </Panel>
        </aside>
      </main>
    </div>
  );
}

// One sidebar panel. On wide screens all three show, unwrapped (the
// sidebar's layout is unchanged); on phones only the chosen tab's.
function Panel({ id, phone, tab, children }) {
  if (!phone) return children;
  if (tab !== id) return null;
  return <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`}>{children}</div>;
}
