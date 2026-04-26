# Church Scheduling System

This project uses one shared backend and groups phase-specific assets under `backend/`, `frontend/`, `docs/`, and `database/`.

It uses:
- MySQL / AWS RDS for the database
- FastAPI for the backend API
- SQLAlchemy and Pydantic for data models
- static HTML pages for admin and member-facing flows

## Current Layout

- `main.py`: shared FastAPI app entry point for all phases
- `models.py`: shared SQLAlchemy and Pydantic models
- `backend/`: shared backend modules and Python dependencies
- `frontend/phase_1/`: admin UI and member signup page
- `frontend/phase_2/`: availability collection page
- `database/phase_1/`: schema and SQL helpers
- `docs/phase_1/`: phase 1 documentation
- `docs/phase_2/`: phase 2 notes and planning
- `scripts/`: startup and stop scripts
- `.env`: local environment variables
- `venv/`: local virtual environment

## Main Links

After startup:

- Admin UI: `http://localhost:8001/phase_1/ui.html`
- Member signup: `http://localhost:8001/phase_1/member_signup.html`
- Availability form: `http://localhost:8001/phase_2/availability_form.html`
- API docs: `http://localhost:8000/docs`

## Run The App

From the project root:

```bash
python main.py
```

Or use the helper script:

```bash
./scripts/run_system.sh
```

## Docs

- `docs/phase_1/QUICKSTART.md`
- `docs/phase_1/API_REFER.md`
- `docs/phase_1/DATABASE_GUIDE.md`
- `docs/phase_1/fastapi_integration.py`
