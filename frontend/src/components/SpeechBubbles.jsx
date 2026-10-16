import { formatCopper } from "../currency.js";

// Speech bubbles over the speakers' heads: HTML laid over the map canvas.
// They are part of the map, not of the page: positions are in percent of
// the map and every size is in container units of the map's width (cqw,
// see .map-stage in index.css), so a bubble keeps the same size relative
// to the villagers and grows or shrinks with the map. A bubble holds the
// line said this tick (one tick = one line), so on the live server each
// line stays up for a tick and then the partner answers. The talking-now
// panel carries the same lines for screen readers, so the overlay itself
// is hidden from them.

const NEAR_TILES = 7;    // bubbles closer than this sideways (their width) stack upwards

export default function SpeechBubbles({ bubbles, positions, width, height }) {
  return (
    <div className="bubble-layer" aria-hidden="true">
      {layout(bubbles, positions).map(({ bubble, pos, level }) => {
        // The tail tip sits just over the head — over the name tag when
        // the tag is drawn above the villager (see layout.js).
        const anchorY = pos.y - (pos.labelBelow ? 0.7 : 1.85);
        return (
          <div
            key={bubble.key}
            className="bubble"
            style={{
              left: `${(pos.x / width) * 100}%`,
              top: `${(anchorY / height) * 100}%`,
              "--level": level,
              "--accent": bubble.color,
            }}
          >
            <span className="bubble-text">{bubble.line.text}</span>
            {bubble.line.offer && (
              <span className="bubble-chip coin">
                {bubble.line.offer.kind === "sell" ? "sells" : "buys"}{" "}
                {bubble.line.offer.quantity} {bubble.line.offer.item.replace("_", " ")} ·{" "}
                {formatCopper(bubble.line.offer.price)}
              </span>
            )}
            {bubble.line.response && (
              <span className={`bubble-chip ${bubble.line.response}`}>
                {bubble.line.response === "accept" ? "✓ accepts" : "✗ refuses"}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Two conversations at the Inn put two speakers a few tiles apart, so the
// later bubble moves up one level instead of covering the first.
function layout(bubbles, positions) {
  const placed = [];
  const sorted = bubbles
    .filter((b) => positions.has(b.speakerId))
    .sort((a, b) => positions.get(a.speakerId).x - positions.get(b.speakerId).x);
  for (const bubble of sorted) {
    const pos = positions.get(bubble.speakerId);
    const level = placed.filter((p) => Math.abs(p.pos.x - pos.x) < NEAR_TILES
                                       && Math.abs(p.pos.y - pos.y) < 8).length;
    placed.push({ bubble, pos, level });
  }
  return placed;
}
