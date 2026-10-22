import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";

const COLORS = { High: "#d9534f", Medium: "#f0ad4e", Low: "#5cb85c" };

export default function Dashboard() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.stats(days).then(setData).catch((e) => setError(e.message));
  }, [days]);

  if (error) return <p className="err">{error}</p>;
  if (!data) return <p className="muted">Loading dashboard…</p>;

  const metrics = data.model_metrics?.targets || {};

  return (
    <div className="dashboard">
      <div className="dash-header">
        <h2>Ticket overview</h2>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={60}>Last 60 days</option>
        </select>
      </div>

      <div className="kpis">
        <Kpi label="Tickets" value={data.total} />
        <Kpi label="Open" value={data.open} />
        <Kpi label="High priority open" value={data.high_priority_open} accent="red" />
        <Kpi label="Resolved by copilot" value={`${Math.round(data.bot_resolution_rate * 100)}%`} accent="green" />
        <Kpi label="Avg resolution time" value={data.avg_resolution_hours != null ? `${data.avg_resolution_hours} h` : "–"} />
      </div>

      <div className="grid two">
        <section className="card">
          <h3>Tickets per day</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.daily} margin={{ left: -20, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot={false} name="Tickets" isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className="card">
          <h3>By category and priority</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.by_category} layout="vertical" margin={{ left: 0, right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} allowDecimals={false} />
              <YAxis type="category" dataKey="category" tick={{ fontSize: 11 }} width={125} interval={0} />
              <Tooltip />
              <Legend />
              {["High", "Medium", "Low"].map((p) => <Bar key={p} dataKey={p} stackId="a" fill={COLORS[p]} isAnimationActive={false} />)}
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>

      <div className="grid two">
        <section className="card">
          <h3>Recurring issues</h3>
          <p className="muted small">Most common phrases in ticket text</p>
          <table className="plain">
            <thead><tr><th>Phrase</th><th>Main category</th><th>Tickets</th></tr></thead>
            <tbody>
              {data.top_phrases.map((t) => (
                <tr key={t.phrase}><td>{t.phrase}</td><td>{t.category}</td><td>{t.count}</td></tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <h3>Classifier performance</h3>
          {Object.keys(metrics).length === 0 ? (
            <p className="muted">No metrics available.</p>
          ) : (
            <>
              <p className="muted small">TF-IDF + Logistic Regression · scores on a held-out 20% test set</p>
              <table className="plain">
                <thead><tr><th>Target</th><th>Trained on</th><th>Accuracy</th><th>Macro F1</th></tr></thead>
                <tbody>
                  {Object.entries(metrics).map(([k, m]) => (
                    <tr key={k}>
                      <td>{k}</td>
                      <td>{m.n_rows?.toLocaleString()} tickets<br /><span className="muted small dataset">{m.dataset}</span></td>
                      <td>{(m.accuracy * 100).toFixed(1)}%</td>
                      <td>{m.macro_f1.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function Kpi({ label, value, accent }) {
  return (
    <div className={`kpi ${accent || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
