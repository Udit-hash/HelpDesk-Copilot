import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../api";

const EXAMPLES = [
  "My VPN says the certificate expired, what do I do?",
  "How do I set up MFA on a new phone?",
  "How many high priority tickets are open right now, by category?",
  "What were the 5 most common issues in the last 7 days?",
];

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const listRef = useRef(null);

  // Scroll the message list (not the whole page) to the newest message.
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function send(text) {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((m) => [...m, { role: "user", content: question }]);
    setInput("");
    setLoading(true);
    try {
      const res = await api.chat(question, history);
      setMessages((m) => [...m, { role: "assistant", content: res.answer, steps: res.steps, sources: res.sources }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `⚠️ ${e.message}`, error: true }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card chat">
      <div className="messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="empty">
            <h2>How can I help?</h2>
            <p>Ask how to fix an IT problem, or ask questions about ticket data.</p>
            <div className="examples">
              {EXAMPLES.map((e) => (
                <button key={e} onClick={() => send(e)}>{e}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role} ${m.error ? "error" : ""}`}>
            <div className="bubble">
              {m.role === "assistant" ? <ReactMarkdown>{m.content}</ReactMarkdown> : m.content}
            </div>
            {m.sources?.length > 0 && (
              <div className="sources">
                Sources: {m.sources.map((s) => <span key={s.source} className="chip">{s.title}</span>)}
              </div>
            )}
            {m.steps?.length > 0 && (
              <details className="steps">
                <summary>How I answered ({m.steps.length} tool call{m.steps.length > 1 ? "s" : ""})</summary>
                {m.steps.map((s, j) => (
                  <div key={j} className="step">
                    <code>{s.tool}</code>
                    <pre>{s.args?.sql || s.args?.query || s.args?.text}</pre>
                    {typeof s.result === "string" ? (
                      <p className="muted">{s.result}</p>
                    ) : s.result?.columns ? (
                      <ResultTable result={s.result} />
                    ) : (
                      <pre>{JSON.stringify(s.result, null, 2)}</pre>
                    )}
                  </div>
                ))}
              </details>
            )}
          </div>
        ))}
        {loading && <div className="msg assistant"><div className="bubble typing">Thinking…</div></div>}
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question…" maxLength={2000} />
        <button type="submit" disabled={loading || !input.trim()}>Send</button>
      </form>
    </section>
  );
}

function ResultTable({ result }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{result.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {result.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{String(v ?? "")}</td>)}</tr>)}
        </tbody>
      </table>
      {result.row_count > result.rows.length && <p className="muted">Showing {result.rows.length} of {result.row_count} rows</p>}
    </div>
  );
}
