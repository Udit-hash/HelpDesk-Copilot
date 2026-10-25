# IT Helpdesk Copilot

An AI assistant for IT support teams. It **answers IT questions from a knowledge base (RAG)**, **classifies new tickets with an ML model trained on 47,837 real IT tickets**, lets engineers **ask questions about ticket data in plain English (text-to-SQL agent built with LangChain)**, and shows a **dashboard** of ticket trends.

**Live demo:** _add your Vercel link here_ · **API docs:** _add your Render link here_/docs

![Chat](docs/screenshots/chat.png)

## Features

| Feature | How it works |
|---|---|
| **AI agent (LangChain)** | A LangChain tool-calling agent chooses between three tools: `search_knowledge_base`, `query_tickets` (read-only SQL) and `classify_ticket`. Every tool call is shown in the UI ("How I answered"). |
| **Knowledge-base Q&A (RAG)** | IT runbooks are split into sections and indexed with TF-IDF. A LangChain retriever returns the best matches as `Document`s, and the LLM answers only from them and cites the articles. |
| **Ticket triage (ML)** | TF-IDF + Logistic Regression predicts the **category** (8 classes, trained on real tickets) and **priority** (High, Medium, Low) with confidence scores. |
| **Self-service suggestions** | When a ticket is raised, the most relevant runbook section is suggested so users can try a fix first. |
| **Dashboard** | Tickets per day, category × priority, recurring phrases in ticket text, copilot resolution rate, average resolution time and live model metrics. |
| **Safe SQL** | LLM-written SQL passes three layers of protection (see [Security](#security)). |
| **Offline mode** | Without an LLM key the app still works: chat returns the best-matching article, and triage and dashboard work fully. |

## Model results

| Model | Training data | Accuracy | Macro F1 |
|---|---|---|---|
| **Category** (8 classes) | 47,837 real IT tickets ([Kaggle](https://www.kaggle.com/datasets/adisongoh/it-service-ticket-classification-dataset)) | **86.1%** | **0.865** |
| Priority (3 classes) | 2,000 synthetic tickets | 56.3% | 0.553 |

Scores are on a held-out, stratified 20% test set. Macro F1 averages the F1 score of every class equally, so small classes like *Administrative rights* count as much as *Hardware*.

**Why priority is trained on synthetic data:** the real dataset has no priority labels. Priority is also hard to predict from text alone (urgency often depends on who is affected, not the words used), which the lower score reflects.

## Architecture

```mermaid
flowchart LR
    U[React frontend<br/>Vercel] -->|REST| API[FastAPI backend<br/>Render]
    API --> AG[LangChain agent<br/>bind_tools loop]
    AG <-->|tool calling| LLM[ChatOpenAI<br/>Groq / OpenAI-compatible]
    AG --> KB[search_knowledge_base<br/>LangChain retriever]
    AG --> SQL[query_tickets<br/>SQL guard + read-only DB]
    AG --> CLF[classify_ticket<br/>scikit-learn]
    KB --> MD[(Markdown runbooks)]
    SQL --> DB[(PostgreSQL / SQLite)]
    API --> CLF
    API --> DB
```

## Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, scikit-learn, pandas
- **AI:** LangChain (`langchain-core`, `langchain-openai`), tool calling, RAG; Groq LLM API (any OpenAI-compatible API works)
- **Database:** PostgreSQL (SQLite works out of the box for quick local runs)
- **Frontend:** React (Vite), Recharts, react-markdown
- **DevOps & security:** GitHub Actions (CI + DevSecOps pipeline), Docker, Gitleaks, Bandit, CodeQL, pip-audit, Trivy, Syft (SBOM), Dependabot; Render (API), Vercel (frontend)

## Run locally

**Requirements:** Python 3.11+ and Node 20.19+ (or 22.12+).

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env             # Windows: copy .env.example .env
uvicorn app.main:app --reload
```

The API runs at http://localhost:8000 (interactive docs at http://localhost:8000/docs).
On first start it creates the database table and loads the tickets from `data/seed_tickets.csv`.
If your database already has tickets from an older version, reload it with `python scripts/reset_db.py`.

**Settings in `backend/.env`:**
- `LLM_API_KEY`: create a free key at [console.groq.com/keys](https://console.groq.com/keys).
- `LLM_MODEL`: a chat model that supports tool calling. To list the models your key can use:
  `python -c "import httpx; from app import config; r=httpx.get(config.LLM_BASE_URL+'/models', headers={'Authorization':'Bearer '+config.LLM_API_KEY}); print('\n'.join(sorted(m['id'] for m in r.json()['data'])))"`
- `DATABASE_URL`: e.g. `postgresql://postgres:YOUR_PASSWORD@localhost:5432/helpdesk` for a local PostgreSQL database (create the empty `helpdesk` database first, for example in pgAdmin). Leave it unset to use SQLite.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env             # VITE_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173.

### 3. Tests

```bash
cd backend
python -m pytest -q
```

25 tests cover the SQL guard, the read-only connection, all API endpoints, and the LangChain agent, including a run of the real `ChatOpenAI` client against a fake OpenAI-compatible API, so tool calling is tested without a real LLM.

## Retrain on the real dataset

The trained model (`backend/models/`) and a sample of real tickets for the database (`backend/data/seed_tickets.csv`) are included. To retrain from scratch:

1. Download `all_tickets_processed_improved_v3.csv` from the [Kaggle dataset page](https://www.kaggle.com/datasets/adisongoh/it-service-ticket-classification-dataset) and save it as `backend/data/raw/all_tickets_processed_improved_v3.csv`.
2. Run:
   ```bash
   cd backend
   python scripts/prepare_real_data.py --reset-db
   ```

This trains the category model on the real tickets, trains the priority model on the synthetic tickets, writes `data/seed_tickets.csv` (3,000 real tickets) and reloads the database. The real dataset only has ticket text and category, so the **priority, dates and status of the seeded tickets are simulated** to give the dashboard something to show.

`scripts/generate_tickets.py` creates the synthetic dataset (`data/tickets.csv`).

## Deploy

**Database:** create a free PostgreSQL database on [Neon](https://neon.tech) or Render and copy its connection URL.

**Backend on Render**
1. New > Web Service > connect this repo. Root directory: `backend` (or use New > Blueprint, which reads `render.yaml`).
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Environment variables: `LLM_API_KEY`, `LLM_MODEL`, `DATABASE_URL`, `PYTHON_VERSION=3.12.7`, and `ALLOWED_ORIGINS=https://<your-app>.vercel.app`

**Frontend on Vercel**
1. New Project > import this repo. Root directory: `frontend` (framework preset: Vite).
2. Environment variable: `VITE_API_URL=https://<your-api>.onrender.com`

> Render's free tier sleeps after inactivity, so the first request can take ~30 seconds.

## Security

Full details, including the threat model and findings log, are in **[SECURITY.md](SECURITY.md)**.

**DevSecOps pipeline** (`.github/workflows/security.yml`), run on every push, pull request and weekly:

| Check | Tool |
|---|---|
| Secrets scanning (code + Git history) | Gitleaks |
| SAST | Bandit (Python), CodeQL (Python + JavaScript) |
| SCA (dependency CVEs) | pip-audit, npm audit, Dependabot |
| Container security | Trivy (Dockerfile + image) |
| SBOM | Syft: CycloneDX + SPDX, published as build artifacts |

Each check is a quality gate: High or Critical findings fail the build. All GitHub Actions are pinned to commit SHAs.

**AI and database safety.** The agent can read ticket data but can never change it:
1. **SQL guard** (`app/sql_guard.py`): only a single `SELECT`/`WITH` statement is accepted; comments, multiple statements and write/DDL keywords are rejected.
2. **Row limit:** at most 50 rows per query.
3. **Read-only connection:** PostgreSQL runs in a `READ ONLY` transaction with a 5-second statement timeout, so even a query that slips past the guard cannot write.

Other measures: non-root container, CORS restricted to the frontend origin, input validation, secrets only in environment variables.

## Project structure

```
backend/
  app/
    main.py          FastAPI routes (chat, tickets, classify, stats)
    agent.py         LangChain tools and agent loop
    llm.py           LangChain ChatOpenAI setup
    retriever.py     Markdown chunking, TF-IDF search, LangChain retriever
    classifier.py    Training, evaluation and prediction
    sql_guard.py     SQL validation
    db.py            Database schema, seeding, read-only queries
  data/kb/           Knowledge-base articles (Markdown)
  data/seed_tickets.csv  Real tickets loaded into the database
  data/tickets.csv   Synthetic tickets (priority model)
  models/            Trained classifier and metrics
  scripts/           Real-data preparation, training, synthetic data generator
  tests/             pytest suite
frontend/
  src/components/    Chat, NewTicket, Dashboard
```

## Screenshots

| Ticket triage | Dashboard |
|---|---|
| ![Ticket](docs/screenshots/ticket.png) | ![Dashboard](docs/screenshots/dashboard.png) |

## Possible improvements

- Neural embeddings (e.g. `bge-small`) with a vector database instead of TF-IDF
- Evaluation set for RAG answer quality
- Authentication and per-user ticket history
- A transformer model (e.g. DistilBERT) for ticket classification
