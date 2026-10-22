import os
import sys
import tempfile
from pathlib import Path

# Use a throwaway database and model for tests, and make sure no real LLM is called.
_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["MODEL_PATH"] = str(_tmp / "classifier.joblib")
os.environ["LLM_API_KEY"] = ""
os.environ["TICKETS_CSV"] = str(Path(__file__).resolve().parents[1] / "data" / "tickets.csv")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs startup: seeds DB and trains the model
        yield c
