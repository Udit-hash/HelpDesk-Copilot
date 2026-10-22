"""The copilot agent, built with LangChain.

LangChain pieces used:
- @tool:           turns Python functions into tools the LLM can call (name, description, argument schema)
- ChatOpenAI:      the chat model (Groq or any OpenAI-compatible API), see llm.py
- bind_tools():    sends the tool schemas to the LLM so it can request tool calls
- Messages:        SystemMessage / HumanMessage / AIMessage / ToolMessage hold the conversation
- BaseRetriever:   KnowledgeBaseRetriever returns LangChain Documents for RAG, see retriever.py

The agent loop (ReAct style): the LLM either answers, or asks for one or more tool calls.
Tool results are added to the conversation and the LLM is called again, until it answers
or AGENT_MAX_STEPS is reached. Every tool call is returned in `steps` so the UI can show
how the answer was produced.
"""
import json
from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from openai import OpenAIError

from . import classifier, config, db, llm
from .retriever import KnowledgeBaseRetriever, get_retriever
from .sql_guard import UnsafeSQLError

kb_retriever = KnowledgeBaseRetriever(k=3)


@tool
def search_knowledge_base(query: str) -> str:
    """Search the IT knowledge base (runbooks and how-to articles). Use for any question about
    fixing an IT problem or how to do something. Input: a short search query, e.g. 'vpn certificate expired'."""
    docs = kb_retriever.invoke(query)
    if not docs:
        return json.dumps({"results": "No matching articles."})
    return json.dumps({"results": [{**d.metadata, "text": d.page_content} for d in docs]})


@tool
def query_tickets(sql: str) -> str:
    """Run ONE read-only SQL SELECT query on the tickets database. Use for questions about ticket
    counts, trends, categories, priorities, resolution times or recurring issues."""
    try:
        return json.dumps(db.run_readonly_query(sql), default=str)
    except UnsafeSQLError as e:
        return json.dumps({"error": f"Query rejected by safety check: {e}"})
    except Exception as e:  # e.g. a SQL syntax error: report it so the LLM can fix the query
        return json.dumps({"error": f"{type(e).__name__}: {str(e)[:300]}"})


@tool
def classify_ticket(text: str) -> str:
    """Predict the category and priority of a support ticket from its text using the trained ML model."""
    return json.dumps(classifier.predict(text))


TOOLS = [search_knowledge_base, query_tickets, classify_ticket]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def system_prompt() -> str:
    return f"""You are IT Helpdesk Copilot, an assistant for employees and IT engineers.

Rules:
- For how-to or troubleshooting questions, ALWAYS call search_knowledge_base first and answer only from
  the returned articles. Mention the article title(s) you used. If the articles do not cover the
  question, say so and suggest raising a ticket.
- For questions about ticket data, call query_tickets. Write SQL for the {db.dialect()} dialect.
  Never modify data. Prefer aggregated queries (COUNT, GROUP BY) over listing rows.
- Never invent steps, links, numbers or policies that are not in tool results.
- Keep answers short: numbered steps for fixes, a one-line summary plus key numbers for data questions.

Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Database schema:
{db.schema_description()}"""


def answer(question: str, history: list[dict] | None = None) -> dict:
    if not llm.is_configured():
        return offline_answer(question)

    messages = [SystemMessage(system_prompt())]
    for m in (history or [])[-6:]:
        content = str(m.get("content") or "")[:2000]
        if m.get("role") == "user" and content:
            messages.append(HumanMessage(content))
        elif m.get("role") == "assistant" and content:
            messages.append(AIMessage(content))
    messages.append(HumanMessage(question))

    model = llm.get_chat_model().bind_tools(TOOLS)
    steps, sources = [], {}
    try:
        for _ in range(config.AGENT_MAX_STEPS):
            ai_msg = model.invoke(messages)
            messages.append(ai_msg)
            if not ai_msg.tool_calls:
                return {"answer": _text(ai_msg.content), "steps": steps,
                        "sources": list(sources.values()), "mode": "llm"}

            for call in ai_msg.tool_calls:
                selected = TOOLS_BY_NAME.get(call["name"])
                output = selected.invoke(call["args"]) if selected else json.dumps({"error": "Unknown tool"})
                messages.append(ToolMessage(content=str(output)[:6000], tool_call_id=call["id"]))

                result = json.loads(output) if isinstance(output, str) else output
                steps.append({"tool": call["name"], "args": call["args"], "result": _summarise(call["name"], result)})
                if call["name"] == "search_knowledge_base" and isinstance(result.get("results"), list):
                    for r in result["results"]:
                        sources.setdefault(r["source"], {"title": r["title"], "source": r["source"]})
    except OpenAIError as e:
        raise llm.LLMError(f"LLM request failed: {e}") from e

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


def _text(content) -> str:
    """AIMessage.content is usually a string, but some providers return a list of content blocks."""
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return content or ""


def _summarise(name: str, result: dict) -> str | dict:
    if "error" in result:
        return result["error"]
    if name == "search_knowledge_base":
        r = result.get("results")
        return f"{len(r)} article section(s) found" if isinstance(r, list) else str(r)
    if name == "query_tickets":
        return {"columns": result["columns"], "rows": result["rows"][:10], "row_count": result["row_count"]}
    return result
