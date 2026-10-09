"""Train prediction models.

    python -m ml.train            # train from the UCI csv files in data/
    python -m ml.train --db       # train from records currently stored in the database
"""
import argparse
import sys

from config import Config
from ml.pipeline import load_csv_dataset, train_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="train from database records")
    args = ap.parse_args()
    if args.db:
        from app import create_app
        from app.ml_service import records_dataframe
        with create_app().app_context():
            df, source = records_dataframe(), "database"
    else:
        df, source = load_csv_dataset(Config.DATA_DIR), "csv"
    print(f"Training on {len(df)} records from {source}")
    report = train_all(df, Config.MODEL_DIR, source=source)
    print("Best models:", report["best"])


if __name__ == "__main__":
    sys.exit(main())
