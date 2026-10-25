"""FastAPI app: chat, ticket creation and dashboard endpoints."""
import logging
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, CountVectorizer

from . import agent, classifier, config, db, llm
from .retriever import get_retriever

log = logging.getLogger("copilot")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db(seed=True)
    if not config.MODEL_PATH.exists():
        log.warning("No trained model found - training on %s", config.SYNTHETIC_CSV)
        classifier.train_and_save(config.SYNTHETIC_CSV, ["title", "description"], "category", "priority",
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
def stats(days: int = Query(30, ge=1, le=365)):
    df = db.load_dataframe()
    if df.empty:
        return {"total": 0}
    recent = df[df["created_at"] >= df["created_at"].max() - pd.Timedelta(days=days)]
    resolved = recent[recent["status"] == "Resolved"]
    hours = (resolved["resolved_at"] - resolved["created_at"]).dt.total_seconds() / 3600

    daily = recent.groupby(recent["created_at"].dt.date).size()
    by_cat_pri = recent.groupby(["category", "priority"]).size().unstack(fill_value=0)
    top_phrases = recurring_phrases(recent)

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
        "top_phrases": top_phrases,
        "model_metrics": classifier.load_metrics(),
    }


# Words that appear in almost every ticket (greetings, sign-offs, dates) and say nothing about the issue.
TICKET_STOP_WORDS = list(ENGLISH_STOP_WORDS | {
    "hi", "hello", "dear", "team", "thanks", "thank", "regards", "kind", "best", "morning", "afternoon",
    "good", "please", "pm", "am", "sent", "re", "fw", "fwd", "ok", "yes", "know", "let", "help", "need",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
    # email signature and header noise in the real dataset
    "importance", "ext", "hub", "analyst", "tel", "mob", "cc", "subject", "date", "wrote",
})


def recurring_phrases(df: pd.DataFrame, top: int = 8, max_per_category: int = 2) -> list[dict]:
    """Most common 2-3 word phrases across tickets, counted once per ticket."""
    if len(df) < 5:
        return []
    text = (df["title"].fillna("") + " " + df["description"].fillna("")).str.lower()
    # Bandit B106 is a false positive: "token_pattern" is a regex for splitting words, not a password.
    vec = CountVectorizer(ngram_range=(2, 3), stop_words=TICKET_STOP_WORDS, min_df=3, binary=True,
                          token_pattern=r"(?u)\b[a-z][a-z]+\b")  # nosec B106
    try:
        matrix = vec.fit_transform(text)
    except ValueError:  # no phrase appears often enough
        return []
    counts = matrix.sum(axis=0).A1
    phrases = vec.get_feature_names_out()
    result, used, per_category = [], set(), {}
    for i in counts.argsort()[::-1]:
        words = set(phrases[i].split())
        if words & used:  # skip overlapping phrases, e.g. "new starter" then "starter form"
            continue
        rows = matrix[:, i].nonzero()[0]
        category = df["category"].iloc[rows].mode().iat[0]
        if per_category.get(category, 0) >= max_per_category:  # keep the list varied
            continue
        result.append({"phrase": phrases[i], "count": int(counts[i]), "category": category})
        per_category[category] = per_category.get(category, 0) + 1
        used |= words
        if len(result) == top:
            break
    return result
