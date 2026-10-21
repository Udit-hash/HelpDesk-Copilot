"""FastAPI app: chat, ticket creation and dashboard endpoints."""
import logging
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent, classifier, config, db, llm
from .retriever import get_retriever

log = logging.getLogger("copilot")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db(seed=True)
    if not config.MODEL_PATH.exists():
        log.warning("No trained model found - training on %s", config.TICKETS_CSV)
        classifier.train_and_save(config.TICKETS_CSV, ["title", "description"], "category", "priority",
                                  config.MODEL_PATH)
    get_retriever()  # build the search index at startup
    yield


app = FastAPI(title="IT Helpdesk Copilot API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS,
                   allow_methods=["GET", "POST"], allow_headers=["*"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = []


class TicketRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=4000)


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


@app.get("/")
def root():
    return {"name": "IT Helpdesk Copilot API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_configured": llm.is_configured(), "llm_model": config.LLM_MODEL,
            "database": db.dialect(), "kb_chunks": len(get_retriever().chunks)}


@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        return agent.answer(req.message, [m.model_dump() for m in req.history])
    except llm.LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/classify")
def classify(req: ClassifyRequest):
    return classifier.predict(req.text)


@app.post("/api/tickets")
def create_ticket(req: TicketRequest):
    """Classify a new ticket, store it, and suggest a self-help article."""
    pred = classifier.predict(req.title, req.description)
    ticket = db.create_ticket(req.title, req.description, pred["category"]["label"],
                              pred.get("priority", {}).get("label", "Medium"))
    hits = get_retriever().search(f"{req.title} {req.description}", k=1, min_score=0.1)
    suggestion = None
    if hits:
        h = hits[0]
        suggestion = {"title": h["title"], "section": h["section"], "source": h["source"],
                      "text": h["text"].split("\n", 1)[-1]}
    return {"ticket": {**ticket, "created_at": str(ticket["created_at"])},
            "prediction": pred, "suggested_article": suggestion}


@app.get("/api/stats")
def stats(days: int = 30):
    df = db.load_dataframe()
    if df.empty:
        return {"total": 0}
    recent = df[df["created_at"] >= df["created_at"].max() - pd.Timedelta(days=days)]
    resolved = recent[recent["status"] == "Resolved"]
    hours = (resolved["resolved_at"] - resolved["created_at"]).dt.total_seconds() / 3600

    daily = recent.groupby(recent["created_at"].dt.date).size()
    by_cat_pri = recent.groupby(["category", "priority"]).size().unstack(fill_value=0)
    top_issues = recent.groupby(["title", "category"]).size().sort_values(ascending=False).head(8)

    return {
        "days": days,
        "total": int(len(recent)),
        "open": int((recent["status"] == "Open").sum()),
        "high_priority_open": int(((recent["status"] == "Open") & (recent["priority"] == "High")).sum()),
        "bot_resolution_rate": round(float(resolved["resolved_by_bot"].mean() or 0), 3) if len(resolved) else 0,
        "avg_resolution_hours": round(float(hours.mean()), 1) if len(hours) else None,
        "daily": [{"date": str(d), "count": int(c)} for d, c in daily.items()],
        "by_category": [{"category": c, **{p: int(row.get(p, 0)) for p in ("High", "Medium", "Low")}}
                        for c, row in by_cat_pri.iterrows()],
        "top_issues": [{"title": t, "category": c, "count": int(n)} for (t, c), n in top_issues.items()],
        "model_metrics": classifier.load_metrics(),
    }
