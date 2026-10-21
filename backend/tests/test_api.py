from app import agent, db, llm


def test_health(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["kb_chunks"] > 0


def test_classify(client):
    r = client.post("/api/classify", json={"text": "VPN keeps disconnecting from home"}).json()
    assert r["category"]["label"] == "Network"
    assert r["priority"]["label"] in {"High", "Medium", "Low"}


def test_create_ticket_suggests_article(client):
    r = client.post("/api/tickets", json={"title": "Forgot my password",
                                          "description": "Cannot log in to my laptop"}).json()
    assert r["ticket"]["category"] == "Access"
    assert r["suggested_article"]["source"] == "password-reset.md"


def test_stats(client):
    r = client.get("/api/stats").json()
    assert r["total"] > 0 and r["daily"] and r["by_category"] and r["model_metrics"]


def test_chat_offline_uses_knowledge_base(client):
    r = client.post("/api/chat", json={"message": "how do I set up MFA on my new phone"}).json()
    assert r["mode"] == "offline"
    assert r["sources"][0]["source"] == "mfa-setup.md"


def test_readonly_connection_blocks_writes(client):
    from sqlalchemy import text
    import pytest
    with pytest.raises(Exception):
        with db.get_readonly_engine().connect() as conn:
            conn.execute(text("DELETE FROM tickets"))
            conn.commit()


def test_agent_tool_loop(client, monkeypatch):
    """Simulate an LLM that calls the SQL tool, then answers."""
    calls = []

    def fake_chat(messages, tools=None, temperature=0.1):
        calls.append(messages)
        if len(calls) == 1:
            return {"content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "query_tickets",
                             "arguments": '{"sql": "SELECT COUNT(*) AS n FROM tickets WHERE status = \'Open\'"}'}}]}
        tool_msg = messages[-1]
        assert tool_msg["role"] == "tool" and '"row_count": 1' in tool_msg["content"]
        return {"content": "There are N open tickets."}

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "chat", fake_chat)
    r = agent.answer("How many tickets are open?")
    assert r["mode"] == "llm" and r["steps"][0]["tool"] == "query_tickets"
    assert r["steps"][0]["result"]["row_count"] == 1


def test_agent_reports_blocked_sql(client, monkeypatch):
    def fake_chat(messages, tools=None, temperature=0.1):
        if messages[-1]["role"] == "user":
            return {"content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "query_tickets", "arguments": '{"sql": "DROP TABLE tickets"}'}}]}
        assert "rejected by safety check" in messages[-1]["content"]
        return {"content": "I can only read ticket data."}

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "chat", fake_chat)
    r = agent.answer("Delete all tickets")
    assert "rejected" in r["steps"][0]["result"]
