"""The copilot agent.

The LLM decides which tool(s) to call:
- search_knowledge_base: RAG over IT runbooks, for "how do I..." questions
- query_tickets: read-only SQL over the ticket database, for data questions
- classify_ticket: the scikit-learn model, to suggest category and priority

The loop runs until the LLM answers without calling a tool, or AGENT_MAX_STEPS is reached.
Every tool call is returned in `steps`, so the UI can show how the answer was produced.
"""
import json
from datetime import datetime

from . import classifier, config, db, llm
from .retriever import get_retriever
from .sql_guard import UnsafeSQLError

TOOLS = [
    {"type": "function", "function": {
        "name": "search_knowledge_base",
        "description": "Search the IT knowledge base (runbooks and how-to articles). Use for any "
                       "question about fixing an IT problem or how to do something.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "search query, e.g. 'vpn certificate expired'"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "query_tickets",
        "description": "Run ONE read-only SQL SELECT query on the tickets database. Use for questions "
                       "about ticket counts, trends, priorities, resolution times or recurring issues.",
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "a single SELECT statement"}},
            "required": ["sql"]}}},
    {"type": "function", "function": {
        "name": "classify_ticket",
        "description": "Predict the category and priority of a support ticket from its text "
                       "using the trained ML model.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "the ticket title and description"}},
            "required": ["text"]}}},
]


def system_prompt() -> str:
    return f"""You are IT Helpdesk Copilot, an assistant for employees and IT engineers.

Rules:
- For how-to or troubleshooting questions, ALWAYS call search_knowledge_base first and answer only from
  the returned articles. Mention the article title(s) you used. If the articles do not cover the
  question, say so and suggest raising a ticket with the right category.
- For questions about ticket data, call query_tickets. Write SQL for the {db.dialect()} dialect.
  Never modify data. Prefer aggregated queries (COUNT, GROUP BY) over listing rows.
- Never invent steps, links, numbers or policies that are not in tool results.
- Keep answers short: numbered steps for fixes, a one-line summary plus key numbers for data questions.

Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Database schema:
{db.SCHEMA_DESCRIPTION}"""


def run_tool(name: str, args: dict) -> dict:
    try:
        if name == "search_knowledge_base":
            hits = get_retriever().search(args.get("query", ""), k=3)
            return {"results": [{"title": h["title"], "section": h["section"], "source": h["source"],
                                 "text": h["text"]} for h in hits] or "No matching articles."}
        if name == "query_tickets":
            return db.run_readonly_query(args.get("sql", ""))
        if name == "classify_ticket":
            return classifier.predict(args.get("text", ""))
        return {"error": f"Unknown tool {name}"}
    except UnsafeSQLError as e:
        return {"error": f"Query rejected by safety check: {e}"}
    except Exception as e:  # report tool errors back to the LLM so it can retry
        return {"error": f"{type(e).__name__}: {e}"}


def answer(question: str, history: list[dict] | None = None) -> dict:
    if not llm.is_configured():
        return offline_answer(question)

    messages = [{"role": "system", "content": system_prompt()}]
    for m in (history or [])[-6:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])[:2000]})
    messages.append({"role": "user", "content": question})

    steps, sources = [], {}
    for _ in range(config.AGENT_MAX_STEPS):
        msg = llm.chat(messages, tools=TOOLS)
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return {"answer": msg.get("content") or "", "steps": steps,
                    "sources": list(sources.values()), "mode": "llm"}

        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(name, args)
            steps.append({"tool": name, "args": args, "result": _summarise(name, result)})
            if name == "search_knowledge_base" and isinstance(result.get("results"), list):
                for r in result["results"]:
                    sources.setdefault(r["source"], {"title": r["title"], "source": r["source"]})
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(result, default=str)[:6000]})

    return {"answer": "I could not finish this request in the allowed number of steps. "
                      "Please rephrase or raise a ticket.",
            "steps": steps, "sources": list(sources.values()), "mode": "llm"}


def offline_answer(question: str) -> dict:
    """Fallback without an LLM key: return the best-matching knowledge base section."""
    hits = get_retriever().search(question, k=3)
    if not hits:
        text = ("I couldn't find a matching article. (Offline mode: set LLM_API_KEY to enable "
                "AI answers and ticket data questions.)")
    else:
        top = hits[0]
        body = top["text"].split("\n", 1)[1] if "\n" in top["text"] else top["text"]
        text = (f"**{top['title']} - {top['section']}**\n\n{body}\n\n"
                "_Offline mode: showing the best-matching article. Set LLM_API_KEY for AI answers._")
    return {"answer": text,
            "steps": [{"tool": "search_knowledge_base", "args": {"query": question},
                       "result": f"{len(hits)} article section(s) found"}],
            "sources": list({h["source"]: {"title": h["title"], "source": h["source"]} for h in hits}.values()),
            "mode": "offline"}


def _summarise(name: str, result: dict) -> str | dict:
    if "error" in result:
        return result["error"]
    if name == "search_knowledge_base":
        r = result.get("results")
        return f"{len(r)} article section(s) found" if isinstance(r, list) else str(r)
    if name == "query_tickets":
        return {"columns": result["columns"], "rows": result["rows"][:10], "row_count": result["row_count"]}
    return result
