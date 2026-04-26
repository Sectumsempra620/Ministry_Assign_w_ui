# Database Guide

This guide describes the current phase 1 database structure.

## Main Files

- `database/phase_1/schema.sql`: raw MySQL schema and seed data
- `models.py`: shared SQLAlchemy representation of the schema
- `database/phase_1/queries.sql`: helper queries

## Core Tables

- `members`
- `roles`
- `member_roles`
- `monthly_forms`
- `service_dates`
- `availability_entries`
- `schedules`
- `role_conflicts`

## Suggested Workflow

1. Load `database/phase_1/schema.sql`
2. Start the API in `main.py`
3. Create members
4. Add role qualifications
5. Create monthly forms
6. Collect availability
7. Create schedules

## Where To Go Next

- Setup: `docs/phase_1/QUICKSTART.md`
- API docs: `docs/phase_1/API_REFER.md`
