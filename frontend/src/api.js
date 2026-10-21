const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  health: () => request("/api/health"),
  chat: (message, history) => request("/api/chat", { method: "POST", body: JSON.stringify({ message, history }) }),
  createTicket: (title, description) =>
    request("/api/tickets", { method: "POST", body: JSON.stringify({ title, description }) }),
  stats: (days = 30) => request(`/api/stats?days=${days}`),
};
