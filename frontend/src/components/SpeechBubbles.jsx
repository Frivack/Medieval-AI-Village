import { formatCopper } from "../currency.js";

// Speech bubbles over the speakers: HTML laid over the map canvas, placed
// in percent of the map so they follow it when it scales down. A bubble
// holds the line said this tick (one tick = one line), so on the live
// server each line stays up for a tick and then the partner answers.
// The talking-now panel carries the same lines for screen readers, so the
// overlay itself is hidden from them.

const NEAR_TILES = 16;   // bubbles closer than this sideways stack upwards

export default function SpeechBubbles({ bubbles, positions, width, height }) {
  const placed = layout(bubbles, positions);
  return (
    <div className="bubble-layer" aria-hidden="true">
      {placed.map(({ bubble, pos, level, below }) => {
        const xFrac = pos.x / width;
        // Keep bubbles inside the map: near an edge, anchor them by that edge.
        const align = xFrac < 0.2 ? "left" : xFrac > 0.8 ? "right" : "center";
        // Above the name tag, or under the villager near the top of the map.
        const anchorY = below ? pos.y + (pos.labelBelow ? 1.9 : 0.9)
                              : pos.y - (pos.labelBelow ? 0.9 : 1.9);
        return (
          <div
            key={bubble.key}
            className={`bubble align-${align}${below ? " below" : ""}`}
            style={{
              left: `${xFrac * 100}%`,
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

// Which way each bubble opens and how far it stacks: two conversations at
// the Inn put two speakers a few tiles apart, so the later bubble moves up
// one level instead of covering the first.
function layout(bubbles, positions) {
  const placed = [];
  const sorted = bubbles
    .filter((b) => positions.has(b.speakerId))
    .sort((a, b) => positions.get(a.speakerId).x - positions.get(b.speakerId).x);
  for (const bubble of sorted) {
    const pos = positions.get(bubble.speakerId);
    const below = pos.y < 15;            // near the top edge: open downwards
    const level = placed.filter((p) => p.below === below
      && Math.abs(p.pos.x - pos.x) < NEAR_TILES && Math.abs(p.pos.y - pos.y) < 8).length;
    placed.push({ bubble, pos, level, below });
  }
  return placed;
}
