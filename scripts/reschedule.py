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

from backend.rescheduler import process_open_reschedule_requests


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply open reschedule requests while keeping the published monthly schedule as stable as possible."
    )
    parser.add_argument("--form-id", type=int, help="Only process requests for one monthly form")
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
        result = process_open_reschedule_requests(db=db, form_id=args.form_id)
    finally:
        db.close()

    print("Applied reschedule weeks:")
    if result.applied_weeks:
        for week_result in result.applied_weeks:
            print(
                f"  Week {week_result.week}: request_ids={week_result.request_ids}, "
                f"changed_schedule_ids={week_result.changed_schedule_ids or 'none'}, note={week_result.note}"
            )
    else:
        print("  None")

    print("Unresolved reschedule weeks:")
    if result.unresolved_weeks:
        for week_result in result.unresolved_weeks:
            print(
                f"  Week {week_result.week}: request_ids={week_result.request_ids}, note={week_result.note}"
            )
    else:
        print("  None")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
