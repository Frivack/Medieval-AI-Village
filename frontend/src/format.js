// Small text helpers shared by the views.

// "Day 3 06:00" -> "06:00": a clock from the API without its day (nothing
// for a missing one, e.g. a conversation that hasn't ended).
export const withoutDay = (clock) => clock?.replace(/^Day \d+ /, "");

// +3 / −2 / 0, with a real minus sign: affinity scores and changes.
export const signed = (n) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");
