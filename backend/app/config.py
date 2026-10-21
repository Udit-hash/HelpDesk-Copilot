"""Application settings, read from environment variables (or a .env file)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"


def _load_dotenv() -> None:
    """Minimal .env loader so no extra dependency is needed."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# LLM: any OpenAI-compatible chat completions API (Groq by default, free tier available).
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

# Database: SQLite by default; set a postgresql:// URL to use PostgreSQL.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'tickets.db'}")
if DATABASE_URL.startswith("postgres://"):  # Render/Heroku style URL
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

TICKETS_CSV = Path(os.getenv("TICKETS_CSV", DATA_DIR / "tickets.csv"))
KB_DIR = Path(os.getenv("KB_DIR", DATA_DIR / "kb"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", MODELS_DIR / "classifier.joblib"))
METRICS_PATH = MODEL_PATH.with_name("metrics.json")

# Comma-separated list of frontend origins allowed to call the API.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

SQL_ROW_LIMIT = int(os.getenv("SQL_ROW_LIMIT", "50"))
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "5"))
