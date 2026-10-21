import { useEffect, useState } from "react";
import { api } from "./api";
import Chat from "./components/Chat.jsx";
import NewTicket from "./components/NewTicket.jsx";
import Dashboard from "./components/Dashboard.jsx";

const TABS = [
  { id: "chat", label: "Ask Copilot" },
  { id: "ticket", label: "Raise Ticket" },
  { id: "dashboard", label: "Dashboard" },
];

export default function App() {
  const [tab, setTab] = useState("chat");
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">🛠️</span>
          <div>
            <h1>IT Helpdesk Copilot</h1>
            <p>AI ticket triage &amp; knowledge assistant</p>
          </div>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "tab active" : "tab"} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="status">
          {healthError ? (
            <span className="pill red">API offline</span>
          ) : !health ? (
            <span className="pill">Connecting…</span>
          ) : health.llm_configured ? (
            <span className="pill green">LLM: {health.llm_model}</span>
          ) : (
            <span className="pill amber">Offline mode (no LLM key)</span>
          )}
        </div>
      </header>

      {healthError && (
        <div className="banner">
          Can't reach the API. If it's hosted on a free tier it may be waking up — wait ~30 seconds and refresh.
        </div>
      )}

      <main className="content">
        {tab === "chat" && <Chat />}
        {tab === "ticket" && <NewTicket />}
        {tab === "dashboard" && <Dashboard />}
      </main>
    </div>
  );
}
