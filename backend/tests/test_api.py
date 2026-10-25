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
    assert r["top_phrases"] and {"phrase", "count", "category"} <= set(r["top_phrases"][0])


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




def test_security_headers(client):
    """Headers added after the OWASP ZAP DAST scan (see SECURITY.md)."""
    h = client.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert h["cross-origin-resource-policy"] == "same-origin"
    assert h["cache-control"] == "no-store"
    assert "cdn.jsdelivr.net" in client.get("/docs").headers["content-security-policy"]


def test_cors_rejects_unknown_origin(client):
    r = client.options("/api/chat", headers={"Origin": "https://evil.example",
                                             "Access-Control-Request-Method": "POST"})
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
