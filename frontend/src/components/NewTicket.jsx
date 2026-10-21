import { useState } from "react";
import { api } from "../api";

export default function NewTicket() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResult(await api.createTicket(title.trim(), description.trim()));
      setTitle("");
      setDescription("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid two">
      <section className="card">
        <h2>Raise a ticket</h2>
        <p className="muted">The ML model predicts the category and priority, and the copilot suggests a self-help article.</p>
        <form onSubmit={submit} className="form">
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Outlook not receiving emails" required minLength={3} maxLength={200} />
          </label>
          <label>
            Description
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={5} maxLength={4000}
              placeholder="What happened? Since when? Is anyone else affected?" />
          </label>
          <button type="submit" disabled={loading || title.trim().length < 3}>{loading ? "Submitting…" : "Submit ticket"}</button>
          {error && <p className="err">{error}</p>}
        </form>
      </section>

      <section className="card">
        <h2>Triage result</h2>
        {!result ? (
          <p className="muted">Submit a ticket to see how it is routed.</p>
        ) : (
          <>
            <p>Ticket <strong>#{result.ticket.id}</strong> created.</p>
            <div className="predictions">
              {Object.entries(result.prediction).map(([k, v]) => (
                <div key={k} className="pred">
                  <span className="muted">{k}</span>
                  <strong className={`tag ${v.label.toLowerCase()}`}>{v.label}</strong>
                  <div className="bar"><div style={{ width: `${Math.round(v.confidence * 100)}%` }} /></div>
                  <span className="muted small">{Math.round(v.confidence * 100)}% confidence</span>
                </div>
              ))}
            </div>
            {result.suggested_article && (
              <div className="suggest">
                <h3>Try this first: {result.suggested_article.title}</h3>
                <p className="muted small">{result.suggested_article.section}</p>
                <pre className="article">{result.suggested_article.text}</pre>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
