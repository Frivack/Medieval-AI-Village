import { useEffect, useRef } from "react";
import { displayPositions } from "../layout.js";
import SpeechBubbles from "./SpeechBubbles.jsx";

// Canvas renderer for the village. 100x50 = 5,000 tiles redrawn per
// frame is trivial for canvas, whereas 5,000 DOM nodes would be slow —
// that's why this is a <canvas> and not a CSS grid. Speech bubbles are
// HTML on top of it (wrapping text is what the browser is good at).

export const SCALE = 12; // canvas pixels per tile

const TILE_COLORS = {
  grass: "#5c8a4e",
  water: "#3f6e96",
  forest: "#315430",
  field: "#c2a25c",
  wall: "#5c4a3d",
  floor: "#d9c3a3",
  door: "#8a6844",
  bridge: "#9c7f57",
};

export const JOB_COLORS = {
  Farmer: "#e0c94f",
  Blacksmith: "#c94f4f",
  Merchant: "#9f5fd0",
  Innkeeper: "#4fb6c9",
};

export default function MapCanvas({ map, villagers, bubbles = [] }) {
  const canvasRef = useRef(null);
  const baseRef = useRef(null); // offscreen canvas with the static tiles
  const positions = displayPositions(villagers, map?.buildings);

  // Draw the static map once (it never changes).
  useEffect(() => {
    if (!map) return;
    const base = document.createElement("canvas");
    base.width = map.width * SCALE;
    base.height = map.height * SCALE;
    const ctx = base.getContext("2d");
    map.rows.forEach((row, y) => {
      [...row].forEach((ch, x) => {
        ctx.fillStyle = TILE_COLORS[map.legend[ch]] ?? "#000";
        ctx.fillRect(x * SCALE, y * SCALE, SCALE, SCALE);
      });
    });
    // Building name labels.
    ctx.font = "bold 11px Georgia, serif";
    ctx.textAlign = "center";
    for (const b of map.buildings) {
      const cx = (b.x + b.width / 2) * SCALE;
      const cy = (b.y - 0.4) * SCALE;
      ctx.fillStyle = "rgba(0,0,0,0.55)";
      ctx.fillRect(cx - 26, cy - 10, 52, 13);
      ctx.fillStyle = "#e8d9b5";
      ctx.fillText(b.name, cx, cy);
    }
    baseRef.current = base;
    drawFrame(canvasRef.current, base, villagers, positions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Redraw agents whenever they move.
  useEffect(() => {
    if (baseRef.current) drawFrame(canvasRef.current, baseRef.current, villagers, positions);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [villagers]);

  if (!map) return <div className="map-loading">Loading map…</div>;
  return (
    <div className="map-stage">
      <canvas
        ref={canvasRef}
        className="map-canvas"
        width={map.width * SCALE}
        height={map.height * SCALE}
      />
      <SpeechBubbles bubbles={bubbles} positions={positions}
                     width={map.width} height={map.height} />
    </div>
  );
}

function drawFrame(canvas, base, villagers, positions) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(base, 0, 0);
  for (const v of villagers) {
    const pos = positions.get(v.id);
    const px = pos.x * SCALE;
    const py = pos.y * SCALE;
    ctx.beginPath();
    ctx.arc(px, py, SCALE * 0.55, 0, Math.PI * 2);
    ctx.fillStyle = JOB_COLORS[v.job] ?? "#fff";
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "#1d1a16";
    ctx.stroke();
    // Name tag above, or below for the lower row of a group, so a crowd
    // at the Inn doesn't stack four tags on top of each other.
    ctx.font = "bold 10px sans-serif";
    ctx.textAlign = "center";
    const w = ctx.measureText(v.name).width + 8;
    const top = pos.labelBelow ? py + SCALE * 0.75 : py - SCALE * 1.75;
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(px - w / 2, top, w, 12);
    ctx.fillStyle = "#fff";
    ctx.fillText(v.name, px, top + 9.5);
  }
}
