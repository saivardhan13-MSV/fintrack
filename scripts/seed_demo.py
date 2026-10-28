"""Load a realistic year of bank activity for a demo user.

    python -m scripts.seed_demo     # writes sample_data/demo_statement.csv and seeds the DB

Then sign in at http://localhost:8000 as demo@fintrack.dev / demo-password-123.
"""

from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from fintrack.config import get_settings
from fintrack.database import Base, make_engine
from fintrack.demo import DEMO_EMAIL, DEMO_PASSWORD, generate_rows, seed, statement_csv

CSV_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "demo_statement.csv"


def main() -> None:
    today = date.today()
    CSV_PATH.parent.mkdir(exist_ok=True)
    CSV_PATH.write_text(statement_csv(generate_rows(today)), encoding="utf-8")

    settings = get_settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        result = seed(db, settings, today)

    print(f"Wrote {result.rows} rows to {CSV_PATH}")
    print(f"Imported {result.imported.imported} "
          f"(skipped {result.imported.duplicates_skipped} duplicates)")
    print(f"Detectable subscriptions: {[d.merchant for d in result.detection.detected]}")
    print(f"Log in as {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
