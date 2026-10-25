"""Train on the real Kaggle dataset and load real tickets into the database.

Dataset: "IT Service Ticket Classification Dataset" (Kaggle, adisongoh)
         file all_tickets_processed_improved_v3.csv, 47,837 real IT support tickets,
         columns: Document (ticket text), Topic_group (one of 8 categories).
Download it from Kaggle and save it as backend/data/raw/all_tickets_processed_improved_v3.csv

What this script does:
1. Trains the CATEGORY model on the real tickets (80/20 stratified split for metrics).
2. Trains the PRIORITY model on the synthetic tickets, because the real dataset has no
   priority labels.
3. Writes data/seed_tickets.csv: a sample of real tickets for the database. The ticket
   text and category are real; priority, dates and status are SIMULATED so the
   dashboard has something to show (the real dataset has none of these fields).
4. With --reset-db, empties the tickets table and reloads it from seed_tickets.csv.

Usage:
    python scripts/prepare_real_data.py --reset-db
"""
import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import classifier, config, db  # noqa: E402

TEXT_COL, LABEL_COL = "Document", "Topic_group"

# Simulated priority mix per category (High, Medium, Low).
PRIORITY_WEIGHTS = {
    "Access": (3, 5, 2), "Administrative rights": (2, 5, 3), "Hardware": (3, 4, 3),
    "Storage": (2, 5, 3), "HR Support": (1, 4, 5), "Internal Project": (1, 5, 4),
    "Miscellaneous": (1, 4, 5), "Purchase": (1, 4, 5),
}
PRIORITIES = ["High", "Medium", "Low"]


def load_real(path: Path) -> pd.DataFrame:
    if not path.exists():
        sys.exit(f"Dataset not found: {path}\nDownload all_tickets_processed_improved_v3.csv from "
                 "https://www.kaggle.com/datasets/adisongoh/it-service-ticket-classification-dataset "
                 "and save it there (see README).")
    df = pd.read_csv(path)
    missing = {TEXT_COL, LABEL_COL} - set(df.columns)
    if missing:
        sys.exit(f"Expected columns {TEXT_COL!r} and {LABEL_COL!r}, found {list(df.columns)}")
    df[TEXT_COL] = df[TEXT_COL].fillna("").astype(str).str.strip()
    df = df[df[TEXT_COL].str.len() > 0].drop_duplicates(subset=TEXT_COL)
    return df.reset_index(drop=True)


def make_title(text: str, words: int = 8) -> str:
    parts = text.split()
    title = " ".join(parts[:words])
    return (title[:1].upper() + title[1:] + ("..." if len(parts) > words else ""))[:200]


def build_seed(df: pd.DataFrame, n: int, days: int, seed: int) -> pd.DataFrame:
    # Bandit B311: non-cryptographic random is fine here; it only simulates sample metadata.
    rng = random.Random(seed)  # nosec B311
    sample = df.sample(n=min(n, len(df)), random_state=seed)
    end = datetime.now().replace(microsecond=0)
    rows = []
    for doc, cat in zip(sample[TEXT_COL], sample[LABEL_COL]):
        priority = rng.choices(PRIORITIES, weights=PRIORITY_WEIGHTS.get(cat, (2, 5, 3)))[0]
        created = end - timedelta(days=rng.random() * days)
        status = "Resolved" if rng.random() < 0.78 else "Open"
        resolved_at, by_bot = "", 0
        if status == "Resolved":
            hours = {"High": 4, "Medium": 18, "Low": 40}[priority]
            resolved_at = (created + timedelta(hours=rng.expovariate(1 / hours))).isoformat(timespec="seconds")
            by_bot = int(rng.random() < 0.35)
        rows.append({"title": make_title(doc), "description": doc[:4000], "category": cat,
                     "priority": priority, "status": status,
                     "created_at": created.isoformat(timespec="seconds"),
                     "resolved_at": resolved_at, "resolved_by_bot": by_bot})
    out = pd.DataFrame(rows).sort_values("created_at").reset_index(drop=True)
    out.insert(0, "id", range(1, len(out) + 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(config.REAL_DATASET_CSV))
    ap.add_argument("--seed-rows", type=int, default=3000, help="real tickets to load into the database")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--reset-db", action="store_true", help="empty the tickets table and reload it")
    args = ap.parse_args()

    df = load_real(Path(args.csv))
    print(f"Loaded {len(df):,} real tickets in {df[LABEL_COL].nunique()} categories")

    print("Training category model on real tickets...")
    cat_model, cat_metrics = classifier.train_target(df[TEXT_COL], df[LABEL_COL].astype(str), Path(args.csv).name)

    print("Training priority model on synthetic tickets (no priority labels in the real data)...")
    texts, labels = classifier.read_texts(config.SYNTHETIC_CSV, ["title", "description"], "priority")
    pri_model, pri_metrics = classifier.train_target(texts, labels, config.SYNTHETIC_CSV.name)

    classifier.save_models({"category": cat_model, "priority": pri_model},
                           {"category": cat_metrics, "priority": pri_metrics}, merge=False)
    print(json.dumps({k: {m: v[m] for m in ("dataset", "n_rows", "accuracy", "macro_f1", "n_test")}
                      for k, v in {"category": cat_metrics, "priority": pri_metrics}.items()}, indent=2))

    seed_path = config.DATA_DIR / "seed_tickets.csv"
    build_seed(df, args.seed_rows, args.days, seed=42).to_csv(seed_path, index=False)
    print(f"Wrote {seed_path}")

    if args.reset_db:
        config.TICKETS_CSV = seed_path
        db.metadata.drop_all(db.get_engine(), tables=[db.tickets])
        db.init_db(seed=True)
        print(f"Database reset and loaded with {min(args.seed_rows, len(df)):,} real tickets")
    else:
        print("Run again with --reset-db to replace the tickets currently in the database.")


if __name__ == "__main__":
    main()
