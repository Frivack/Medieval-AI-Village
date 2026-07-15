import { useEffect, useRef } from "react";

// Canvas renderer for the village. 100x50 = 5,000 tiles redrawn per
// frame is trivial for canvas, whereas 5,000 DOM nodes would be slow —
// that's why this is a <canvas> and not a CSS grid.

const SCALE = 12; // canvas pixels per tile

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

const JOB_COLORS = {
  Farmer: "#e0c94f",
  Blacksmith: "#c94f4f",
  Merchant: "#9f5fd0",
  Innkeeper: "#4fb6c9",
};

export default function MapCanvas({ map, villagers }) {
  const canvasRef = useRef(null);
  const baseRef = useRef(null); // offscreen canvas with the static tiles

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
    drawFrame(canvasRef.current, base, villagers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Redraw agents whenever they move.
  useEffect(() => {
    if (baseRef.current) drawFrame(canvasRef.current, baseRef.current, villagers);
  }, [villagers]);

  if (!map) return <div className="map-loading">Loading map…</div>;
  return (
    <canvas
      ref={canvasRef}
      className="map-canvas"
      width={map.width * SCALE}
      height={map.height * SCALE}
    />
  );
}

function drawFrame(canvas, base, villagers) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(base, 0, 0);
  for (const v of villagers) {
    const px = v.x * SCALE + SCALE / 2;
    const py = v.y * SCALE + SCALE / 2;
    ctx.beginPath();
    ctx.arc(px, py, SCALE * 0.55, 0, Math.PI * 2);
    ctx.fillStyle = JOB_COLORS[v.job] ?? "#fff";
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "#1d1a16";
    ctx.stroke();
    ctx.font = "bold 10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(px - 24, py - SCALE * 1.9, 48, 12);
    ctx.fillStyle = "#fff";
    ctx.fillText(v.name, px, py - SCALE * 1.1);
  }
}
