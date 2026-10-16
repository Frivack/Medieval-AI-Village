// Thin fetch wrappers around the FastAPI backend.
// Paths are relative so they work both behind the vite dev proxy
// and when FastAPI serves the built frontend on the same origin.

async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

export const fetchMap = () => getJSON("/map");
export const fetchVillagers = () => getJSON("/villagers");
// One villager in full: schedule ahead, relationships both ways, memories.
export const fetchVillager = (id) => getJSON(`/villagers/${encodeURIComponent(id)}`);
export const fetchTime = () => getJSON("/time");
export const fetchStatus = () => getJSON("/status");
// Newest first: the active ones plus the last few that ended, with lines,
// offers, deals and what each side made of it afterwards.
export const fetchConversations = (limit = 10) => getJSON(`/conversations?limit=${limit}`);

export async function advanceTicks(count = 1) {
  const res = await fetch(`/tick?count=${count}`, { method: "POST" });
  if (!res.ok) throw new Error(`/tick -> HTTP ${res.status}`);
  return res.json();
}
