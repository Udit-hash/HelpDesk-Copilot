"""Train the ticket classifier (category + priority) and save metrics.

Model: TF-IDF (word 1-2 grams) + Logistic Regression, one model per target.

Usage:
    python scripts/train_classifier.py                       # uses data/tickets.csv
    python scripts/train_classifier.py --csv my_data.csv \
        --text-cols "Document" --category-col "Topic_group"  # e.g. a Kaggle dataset
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.classifier import train_and_save  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(config.TICKETS_CSV))
    ap.add_argument("--text-cols", default="title,description",
                    help="comma-separated columns joined to form the ticket text")
    ap.add_argument("--category-col", default="category")
    ap.add_argument("--priority-col", default="priority",
                    help="set to '' if the dataset has no priority column")
    ap.add_argument("--out", default=str(config.MODEL_PATH))
    args = ap.parse_args()

    metrics = train_and_save(
        csv_path=Path(args.csv),
        text_cols=[c.strip() for c in args.text_cols.split(",") if c.strip()],
        category_col=args.category_col,
        priority_col=args.priority_col or None,
        out_path=Path(args.out),
    )
    print(json.dumps({k: {m: v[m] for m in ("accuracy", "macro_f1", "n_test")}
                      for k, v in metrics["targets"].items()}, indent=2))
    print(f"Saved model to {args.out}")


if __name__ == "__main__":
    main()
