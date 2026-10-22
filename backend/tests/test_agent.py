"""Agent tests. No real LLM is called.

test_agent_with_fake_openai_server runs the real LangChain ChatOpenAI client against a fake
OpenAI-compatible HTTP API, so the full request/response format (tool schemas, tool calls,
tool results) is exercised exactly as it would be with Groq.
"""
import json

import httpx
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from app import agent, llm


class ScriptedModel:
    """Minimal stand-in for a LangChain chat model: returns pre-written AIMessages in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        return self.replies.pop(0)


def use_model(monkeypatch, model):
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "get_chat_model", lambda: model)


def test_tools_are_langchain_tools():
    names = {t.name for t in agent.TOOLS}
    assert names == {"search_knowledge_base", "query_tickets", "classify_ticket"}
    assert "sql" in agent.query_tickets.args


def test_agent_runs_sql_tool_then_answers(client, monkeypatch):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"name": "query_tickets", "id": "call_1",
                                            "args": {"sql": "SELECT COUNT(*) AS n FROM tickets WHERE status = 'Open'"}}]),
        AIMessage(content="There are N open tickets."),
    ])
    use_model(monkeypatch, model)
    r = agent.answer("How many tickets are open?")
    assert r["mode"] == "llm" and r["answer"] == "There are N open tickets."
    assert r["steps"][0]["tool"] == "query_tickets" and r["steps"][0]["result"]["row_count"] == 1
    tool_msg = model.calls[1][-1]
    assert tool_msg.type == "tool" and tool_msg.tool_call_id == "call_1"


def test_agent_collects_kb_sources(client, monkeypatch):
    use_model(monkeypatch, ScriptedModel([
        AIMessage(content="", tool_calls=[{"name": "search_knowledge_base", "id": "c1",
                                            "args": {"query": "reset MFA new phone"}}]),
        AIMessage(content="Follow the MFA Setup article."),
    ]))
    r = agent.answer("How do I set up MFA on a new phone?")
    assert r["sources"][0]["source"] == "mfa-setup.md"


def test_agent_reports_blocked_sql(client, monkeypatch):
    model = ScriptedModel([
        AIMessage(content="", tool_calls=[{"name": "query_tickets", "id": "c1",
                                            "args": {"sql": "DROP TABLE tickets"}}]),
        AIMessage(content="I can only read ticket data."),
    ])
    use_model(monkeypatch, model)
    r = agent.answer("Delete all tickets")
    assert "rejected" in r["steps"][0]["result"]
    assert "rejected by safety check" in model.calls[1][-1].content


def test_agent_with_fake_openai_server(client, monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            assert {t["function"]["name"] for t in body["tools"]} == {
                "search_knowledge_base", "query_tickets", "classify_ticket"}
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_abc", "type": "function",
                "function": {"name": "classify_ticket", "arguments": json.dumps({"text": "VPN keeps dropping"})}}]}
        else:
            tool_msg = body["messages"][-1]
            assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call_abc"
            assert body["messages"][-2]["tool_calls"][0]["id"] == "call_abc"
            message = {"role": "assistant", "content": "That looks like a Network ticket."}
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "fake-model",
            "choices": [{"index": 0, "message": message,
                         "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    model = ChatOpenAI(model="fake-model", api_key="test", base_url="https://fake.local/v1",
                       http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
    use_model(monkeypatch, model)
    r = agent.answer("What category is 'VPN keeps dropping'?")
    assert r["answer"] == "That looks like a Network ticket."
    assert r["steps"][0]["tool"] == "classify_ticket"
    assert r["steps"][0]["result"]["category"]["label"] == "Network"
    assert len(requests) == 2


def test_llm_errors_become_502(client, monkeypatch):
    def handler(request):
        return httpx.Response(404, json={"error": {"message": "The model does not exist", "code": "model_not_found"}})

    model = ChatOpenAI(model="missing", api_key="test", base_url="https://fake.local/v1",
                       http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
    use_model(monkeypatch, model)
    r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 502 and "does not exist" in r.json()["detail"]
