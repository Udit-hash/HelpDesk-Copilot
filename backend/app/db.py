"""Ticket database (SQLite by default, PostgreSQL via DATABASE_URL)."""
from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd
from sqlalchemy import (Boolean, Column, DateTime, Integer, MetaData, String, Table, Text,
                        create_engine, func, insert, select, text)
from sqlalchemy.engine import Engine

from . import config
from .sql_guard import validate_select

metadata = MetaData()

tickets = Table(
    "tickets", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("category", String(40), nullable=False),
    Column("priority", String(10), nullable=False),
    Column("status", String(20), nullable=False, default="Open"),
    Column("created_at", DateTime, nullable=False),
    Column("resolved_at", DateTime, nullable=True),
    Column("resolved_by_bot", Boolean, nullable=False, default=False),
)

# Shown to the LLM so it can write correct SQL.
SCHEMA_DESCRIPTION = """Table: tickets
- id INTEGER primary key
- title TEXT: short summary written by the user
- description TEXT: full ticket text
- category TEXT: one of 'Network', 'Access', 'Hardware', 'Software', 'Email'
- priority TEXT: one of 'High', 'Medium', 'Low'
- status TEXT: 'Open' or 'Resolved'
- created_at TIMESTAMP: when the ticket was raised
- resolved_at TIMESTAMP: when it was resolved (NULL if open)
- resolved_by_bot BOOLEAN: true if the copilot resolved it without an engineer"""


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
    return create_engine(config.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_readonly_engine() -> Engine:
    url = config.DATABASE_URL
    if url.startswith("sqlite:///"):
        path = url.removeprefix("sqlite:///")
        return create_engine(f"sqlite:///file:{path}?mode=ro&uri=true",
                             connect_args={"check_same_thread": False})
    return get_engine()


def dialect() -> str:
    return get_engine().dialect.name


def init_db(seed: bool = True) -> None:
    """Create tables and, if empty, load the sample tickets.

    Sample dates are shifted so the newest ticket is "now", keeping the
    dashboard's "last 30 days" view populated whenever the app is deployed.
    """
    engine = get_engine()
    metadata.create_all(engine)
    if not seed or not config.TICKETS_CSV.exists():
        return
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(tickets)).scalar():
            return
        df = pd.read_csv(config.TICKETS_CSV)
        created = pd.to_datetime(df["created_at"])
        resolved = pd.to_datetime(df["resolved_at"], errors="coerce")
        shift = datetime.now().replace(microsecond=0) - created.max().to_pydatetime() - timedelta(hours=1)
        rows = [{
            "title": r.title, "description": r.description, "category": r.category,
            "priority": r.priority, "status": r.status,
            "created_at": (c + shift).to_pydatetime(),
            "resolved_at": None if pd.isna(res) else (res + shift).to_pydatetime(),
            "resolved_by_bot": bool(r.resolved_by_bot),
        } for r, c, res in zip(df.itertuples(), created, resolved)]
        conn.execute(insert(tickets), rows)


def create_ticket(title: str, description: str, category: str, priority: str) -> dict:
    with get_engine().begin() as conn:
        result = conn.execute(insert(tickets).values(
            title=title, description=description, category=category, priority=priority,
            status="Open", created_at=datetime.now().replace(microsecond=0), resolved_by_bot=False,
        ).returning(*tickets.c))
        return dict(result.mappings().one())


def run_readonly_query(sql: str) -> dict:
    """Validate and run LLM-written SQL on a read-only connection."""
    safe_sql = validate_select(sql, config.SQL_ROW_LIMIT)
    engine = get_readonly_engine()
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '5s'"))
        result = conn.execute(text(safe_sql))
        columns = list(result.keys())
        rows = [[_jsonable(v) for v in row] for row in result.fetchall()]
        conn.rollback()
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


def _jsonable(v):
    if isinstance(v, datetime):
        return v.isoformat(sep=" ", timespec="minutes")
    return v


def load_dataframe() -> pd.DataFrame:
    with get_engine().connect() as conn:
        df = pd.read_sql(select(tickets), conn)
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["resolved_at"] = pd.to_datetime(df["resolved_at"], errors="coerce")
    return df
