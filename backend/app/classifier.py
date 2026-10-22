"""Ticket classifier: predicts category and priority from ticket text.

Each target has its own TF-IDF + Logistic Regression pipeline. Targets can be
trained on different datasets (e.g. category on real tickets, priority on the
synthetic set, because the real dataset has no priority labels).
"""
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
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=200_000,
                                  sublinear_tf=True, stop_words="english")),
        ("clf", LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")),
    ])


def train_target(texts: pd.Series, labels: pd.Series, dataset: str) -> tuple[Pipeline, dict]:
    """Evaluate on a stratified 80/20 split, then refit on all data for the saved model."""
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels)
    pred = build_pipeline().fit(X_train, y_train).predict(X_test)
    metrics = {
        "dataset": dataset,
        "n_rows": int(len(texts)),
        "n_classes": int(labels.nunique()),
        "accuracy": round(accuracy_score(y_test, pred), 4),
        "macro_f1": round(f1_score(y_test, pred, average="macro"), 4),
        "n_test": int(len(y_test)),
        "report": classification_report(y_test, pred, output_dict=True, zero_division=0),
    }
    return build_pipeline().fit(texts, labels), metrics


def read_texts(csv_path: Path, text_cols: list[str], label_col: str) -> tuple[pd.Series, pd.Series]:
    df = pd.read_csv(csv_path)
    missing = [c for c in text_cols + [label_col] if c not in df]
    if missing:
        raise ValueError(f"Columns not found in {csv_path.name}: {missing}. Available: {list(df.columns)}")
    df = df.dropna(subset=[label_col])
    texts = df[text_cols].fillna("").astype(str).agg(" ".join, axis=1).str.strip()
    keep = texts.str.len() > 0
    return texts[keep], df.loc[keep, label_col].astype(str)


def save_models(models: dict, metrics: dict, out_path: Path = None, merge: bool = True) -> None:
    """Save models and metrics. With merge=True, targets not given keep their existing model."""
    out_path = out_path or config.MODEL_PATH
    metrics_path = out_path.with_name("metrics.json")
    all_models, all_metrics = {}, {}
    if merge and out_path.exists():
        all_models = joblib.load(out_path)
        if metrics_path.exists():
            all_metrics = json.loads(metrics_path.read_text()).get("targets", {})
    all_models.update(models)
    all_metrics.update(metrics)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(all_models, out_path, compress=3)
    metrics_path.write_text(json.dumps(
        {"trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "targets": all_metrics}, indent=2))
    load_models.cache_clear()


def train_and_save(csv_path: Path, text_cols: list[str], category_col: str,
                   priority_col: str | None, out_path: Path, merge: bool = False) -> dict:
    """Train category (and optionally priority) from one CSV and save them."""
    targets = {"category": category_col, **({"priority": priority_col} if priority_col else {})}
    models, metrics = {}, {}
    for name, col in targets.items():
        texts, labels = read_texts(csv_path, text_cols, col)
        models[name], metrics[name] = train_target(texts, labels, csv_path.name)
    save_models(models, metrics, out_path, merge=merge)
    return {"targets": metrics}


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
