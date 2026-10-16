import { useCallback, useEffect, useRef, useState } from "react";
import { displayPositions } from "../layout.js";
import SpeechBubbles from "./SpeechBubbles.jsx";
import TerrainCanvas from "./TerrainCanvas.jsx";
import VillagerLayer from "./VillagerLayer.jsx";

// The village map with zoom and pan. Terrain canvas at the bottom,
// villagers and names on it, speech bubbles on top — all inside one
// "world" element that gets a single translate+scale, so everything
// zooms together (bubbles too: they're sized in map units).
//
//   wheel            zoom around the pointer
//   + / − / Fit      zoom around the centre, back to the whole map
//   drag             move the map (when zoomed in)
//   two fingers      pinch to zoom and move (phones)
//
// The view is {z, x, y}: scale and offset in px of the world inside the
// viewport. It is clamped so the map always fills the viewport.

const MIN_ZOOM = 1;      // the whole map, as before
const MAX_ZOOM = 4;
const BUTTON_STEP = 1.5;
const TAP_SLOP = 5;      // px a press may move and still count as a tap, not a drag

const clampZoom = (z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

function clampView(v, { w, h }) {
  const z = clampZoom(v.z);
  return { z, x: Math.min(0, Math.max(w - w * z, v.x)), y: Math.min(0, Math.max(h - h * z, v.y)) };
}

export default function MapView({ map, villagers, bubbles = [], selectedId, onSelect }) {
  const viewportRef = useRef(null);
  const size = useRef({ w: 1, h: 1 });
  const pointers = useRef(new Map());   // pointerId -> last {x, y}, for drag and pinch
  // A press that hasn't moved yet: {id, x, y, villager}. Lifting it there
  // is a tap, which opens the villager under it; moving turns it into a drag.
  const tap = useRef(null);
  const [view, setView] = useState({ z: 1, x: 0, y: 0 });

  // Zoom by `factor`, keeping the map point under (cx, cy) where it is.
  const zoomAt = useCallback((factor, cx, cy) => setView((v) => {
    const z = clampZoom(v.z * factor);
    const k = z / v.z;
    return clampView({ z, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k }, size.current);
  }), []);

  // Track the viewport's size (the window can change), re-clamping the view.
  // Measured once right away too: the observer only reports when the page
  // renders, and a zoom before that would clamp against a 1x1 map.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return undefined;
    const r = el.getBoundingClientRect();
    size.current = { w: r.width, h: r.height };
    const ro = new ResizeObserver(([entry]) => {
      size.current = { w: entry.contentRect.width, h: entry.contentRect.height };
      setView((v) => clampView(v, size.current));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [map]);

  // Wheel zoom. Registered by hand because React's onWheel is passive, and
  // preventDefault is what stops the page from scrolling under the map.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;   // lines -> px (Firefox)
      zoomAt(Math.exp(-dy * 0.0015), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [map, zoomAt]);

  const onPointerDown = (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    // Read the target before capturing: capture redirects later events.
    const villager = e.target.closest?.("[data-villager]")?.dataset.villager ?? null;
    tap.current = pointers.current.size === 0
      ? { id: e.pointerId, x: e.clientX, y: e.clientY, villager } : null;   // a 2nd finger: no tap
    // Keep receiving moves when the pointer leaves the map mid-drag.
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
  };

  const onPointerMove = (e) => {
    const pts = pointers.current;
    if (!pts.has(e.pointerId)) return;
    const t = tap.current;
    if (t && Math.hypot(e.clientX - t.x, e.clientY - t.y) > TAP_SLOP) tap.current = null;
    const r = viewportRef.current.getBoundingClientRect();
    if (pts.size === 1) {                                  // drag: move the map
      const last = pts.get(e.pointerId);
      const dx = e.clientX - last.x, dy = e.clientY - last.y;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      setView((v) => clampView({ ...v, x: v.x + dx, y: v.y + dy }, size.current));
    } else if (pts.size === 2) {                           // pinch: zoom and move
      const [a0, b0] = [...pts.values()];
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const [a1, b1] = [...pts.values()];
      const d0 = Math.hypot(a0.x - b0.x, a0.y - b0.y);
      const d1 = Math.hypot(a1.x - b1.x, a1.y - b1.y);
      if (d0 === 0) return;
      const m0 = { x: (a0.x + b0.x) / 2 - r.left, y: (a0.y + b0.y) / 2 - r.top };
      const m1 = { x: (a1.x + b1.x) / 2 - r.left, y: (a1.y + b1.y) / 2 - r.top };
      setView((v) => {
        const z = clampZoom(v.z * (d1 / d0));
        const k = z / v.z;
        return clampView({ z, x: m1.x - (m0.x - v.x) * k, y: m1.y - (m0.y - v.y) * k }, size.current);
      });
    }
  };

  const onPointerEnd = (e) => {
    pointers.current.delete(e.pointerId);
    const t = tap.current;
    tap.current = null;
    if (e.type === "pointerup" && t?.id === e.pointerId && t.villager && onSelect) onSelect(t.villager);
  };

  if (!map) return <div className="map-loading">Loading map…</div>;
  const positions = displayPositions(villagers, map.buildings);
  const zoomed = view.z > MIN_ZOOM;
  const centre = () => [size.current.w / 2, size.current.h / 2];
  return (
    <div
      ref={viewportRef}
      className={`map-view${zoomed ? " zoomed" : ""}`}
      // At the whole-map zoom a one-finger swipe still scrolls the page;
      // zoomed in, it moves the map. Two fingers always pinch the map.
      style={{ touchAction: zoomed ? "none" : "pan-y" }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
    >
      <div
        className="map-world"
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})` }}
      >
        <div className="map-stage">
          <TerrainCanvas map={map} />
          <VillagerLayer map={map} villagers={villagers} positions={positions}
                         selectedId={selectedId} />
          <SpeechBubbles bubbles={bubbles} positions={positions}
                         width={map.width} height={map.height} />
        </div>
      </div>
      {/* Buttons don't start a drag. */}
      <div className="map-zoom" onPointerDown={(e) => e.stopPropagation()}>
        <button type="button" aria-label="Zoom in" title="Zoom in (or scroll on the map)"
                disabled={view.z >= MAX_ZOOM} onClick={() => zoomAt(BUTTON_STEP, ...centre())}>+</button>
        <button type="button" aria-label="Zoom out" title="Zoom out"
                disabled={!zoomed} onClick={() => zoomAt(1 / BUTTON_STEP, ...centre())}>−</button>
        <button type="button" aria-label="Show the whole map" title="Show the whole map"
                disabled={!zoomed} onClick={() => setView({ z: 1, x: 0, y: 0 })}>Fit</button>
        <span className="map-zoom-level" aria-live="polite">{view.z.toFixed(1)}×</span>
      </div>
    </div>
  );
}
