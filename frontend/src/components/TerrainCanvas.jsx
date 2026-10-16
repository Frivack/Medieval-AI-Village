import { memo, useEffect, useRef } from "react";

// The terrain: grass, water, fields, walls and floors, drawn once.
// 100x50 = 5,000 tiles on a canvas is trivial, whereas 5,000 DOM nodes
// would be slow — that's why this is a <canvas> and not a CSS grid.
// Everything that moves or has text (villagers, names, speech bubbles)
// is HTML on top of it, so it stays sharp when the map is zoomed; the
// tiles themselves scale up as pixel art.

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

function TerrainCanvas({ map }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const ctx = canvasRef.current.getContext("2d");
    map.rows.forEach((row, y) => {
      [...row].forEach((ch, x) => {
        ctx.fillStyle = TILE_COLORS[map.legend[ch]] ?? "#000";
        ctx.fillRect(x * SCALE, y * SCALE, SCALE, SCALE);
      });
    });
  }, [map]);

  return (
    <canvas
      ref={canvasRef}
      className="map-canvas"
      width={map.width * SCALE}
      height={map.height * SCALE}
      role="img"
      aria-label={`Map of the village: ${map.buildings.map((b) => b.name).join(", ")}`}
    />
  );
}

// The map never changes, so zooming and polling never redraw it.
export default memo(TerrainCanvas);
