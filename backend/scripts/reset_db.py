"""Empty the tickets table and reload it from the seed file.

Uses data/seed_tickets.csv (real tickets) if it exists, otherwise data/tickets.csv.
Run this after switching datasets, e.g. if your database still holds the old synthetic tickets.

Usage:
    python scripts/reset_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db  # noqa: E402

if __name__ == "__main__":
    print(f"Database: {db.dialect()}  |  loading {config.TICKETS_CSV.name}")
    db.metadata.drop_all(db.get_engine(), tables=[db.tickets])
    db.init_db(seed=True)
    print(f"Done: {len(db.load_dataframe()):,} tickets loaded.")
