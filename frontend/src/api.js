const BASE_URL = "http://localhost:8001";

// Hardcoded for demo — Margaret's user ID
export const MARGARET_ID = "a1acdb4d-f45d-4ee0-a46d-f356d3c2328c";

export async function fetchCalls() {
  const res = await fetch(`${BASE_URL}/calls/${MARGARET_ID}`);
  if (!res.ok) throw new Error("Failed to fetch calls");
  return res.json();
}

export async function fetchMoodHistory() {
  const res = await fetch(`${BASE_URL}/mood/${MARGARET_ID}`);
  if (!res.ok) throw new Error("Failed to fetch mood history");
  return res.json();
}

export async function fetchMemories() {
  const res = await fetch(`${BASE_URL}/memory/${MARGARET_ID}`);
  if (!res.ok) throw new Error("Failed to fetch memories");
  return res.json();
}
