const BASE_URL = "http://localhost:8001";

export async function fetchUsers() {
  const res = await fetch(`${BASE_URL}/users/`);
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function fetchCalls(userId) {
  const res = await fetch(`${BASE_URL}/calls/${userId}`);
  if (!res.ok) throw new Error("Failed to fetch calls");
  return res.json();
}

export async function fetchMoodHistory(userId) {
  const res = await fetch(`${BASE_URL}/mood/${userId}`);
  if (!res.ok) throw new Error("Failed to fetch mood history");
  return res.json();
}

export async function fetchMemories(userId) {
  const res = await fetch(`${BASE_URL}/memory/${userId}`);
  if (!res.ok) throw new Error("Failed to fetch memories");
  return res.json();
}
