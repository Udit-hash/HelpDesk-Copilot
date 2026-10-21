"""Ticket classifier: predicts category and priority from ticket text."""
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from . import config


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words="english")),
        ("clf", LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")),
    ])


def train_and_save(csv_path: Path, text_cols: list[str], category_col: str,
                   priority_col: str | None, out_path: Path) -> dict:
    df = pd.read_csv(csv_path)
    missing = [c for c in text_cols + [category_col] + ([priority_col] if priority_col else []) if c not in df]
    if missing:
        raise ValueError(f"Columns not found in {csv_path.name}: {missing}. Available: {list(df.columns)}")

    text = df[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
    targets = {"category": category_col}
    if priority_col:
        targets["priority"] = priority_col

    models, metrics = {}, {"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "dataset": csv_path.name, "n_rows": len(df), "targets": {}}
    for name, col in targets.items():
        y = df[col].astype(str)
        X_train, X_test, y_train, y_test = train_test_split(
            text, y, test_size=0.2, random_state=42, stratify=y)
        pipe = build_pipeline().fit(X_train, y_train)
        pred = pipe.predict(X_test)
        metrics["targets"][name] = {
            "accuracy": round(accuracy_score(y_test, pred), 4),
            "macro_f1": round(f1_score(y_test, pred, average="macro"), 4),
            "n_test": len(y_test),
            "report": classification_report(y_test, pred, output_dict=True, zero_division=0),
        }
        # Refit on all data for the saved model.
        models[name] = build_pipeline().fit(text, y)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, out_path)
    out_path.with_name("metrics.json").write_text(json.dumps(metrics, indent=2))
    load_models.cache_clear()
    return metrics


@lru_cache(maxsize=1)
def load_models() -> dict:
    if not config.MODEL_PATH.exists():
        raise FileNotFoundError("Model not trained yet. Run: python scripts/train_classifier.py")
    return joblib.load(config.MODEL_PATH)


def predict(title: str, description: str = "") -> dict:
    models = load_models()
    text = f"{title} {description}".strip()
    result = {}
    for name, pipe in models.items():
        proba = pipe.predict_proba([text])[0]
        best = proba.argmax()
        result[name] = {"label": str(pipe.classes_[best]), "confidence": round(float(proba[best]), 3)}
    return result


def load_metrics() -> dict | None:
    if not config.METRICS_PATH.exists():
        return None
    m = json.loads(config.METRICS_PATH.read_text())
    for t in m.get("targets", {}).values():
        t.pop("report", None)
    return m
