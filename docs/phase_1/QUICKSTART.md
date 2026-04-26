# Quick Start

The project now uses shared top-level folders with phase-specific subfolders.

## Important Paths

- Backend entry point: `main.py`
- Shared models: `models.py`
- Backend modules and dependencies: `backend/`
- Frontend root: `frontend/`
- Phase 1 frontend pages: `frontend/phase_1/`
- Phase 2 frontend pages: `frontend/phase_2/`
- Database files: `database/phase_1/`
- Scripts: `scripts/`
- Environment file: `.env`

## Start The System

From the project root:

```bash
python main.py
```

Or:

```bash
./scripts/run_system.sh
```

## URLs

- Admin UI: `http://localhost:8001/phase_1/ui.html`
- Member signup page: `http://localhost:8001/phase_1/member_signup.html`
- Availability form: `http://localhost:8001/phase_2/availability_form.html`
- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Python Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

## Database Setup

Schema file:

```bash
database/phase_1/schema.sql
```

Helper queries:

```bash
database/phase_1/queries.sql
```

## Environment Setup

Put your database connection in the root `.env` file:

```env
DATABASE_URL="mysql+pymysql://admin:YOUR_PASSWORD@YOUR_DB_HOST:3306/church_tech_ministry"
```

## Notes

- The admin page and member signup page are intentionally separate.
- The startup script expects `.env` and `venv/` at the project root.
- The member signup page only exposes registration, not admin tools.
