#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.scheduler import generate_schedule


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate service schedules from availability and qualifications.")
    parser.add_argument("--form-id", type=int, required=True, help="Monthly form id to schedule")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing schedules for the form before regenerating",
    )
    args = parser.parse_args()

    load_dotenv(override=True)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        poolclass=NullPool,
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_local()

    try:
        result = generate_schedule(
            form_id=args.form_id,
            db=db,
            replace_existing=args.replace_existing,
        )
    finally:
        db.close()

    print(f"Created {len(result.created)} schedule rows for form {args.form_id}.")
    if result.gaps:
        print("Unfilled gaps:")
        for gap in result.gaps:
            print(
                f"  Week {gap.week} | {gap.role_name} | filled {gap.filled_slots}/{gap.required_slots} | {gap.reason}"
            )
    else:
        print("No gaps detected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
