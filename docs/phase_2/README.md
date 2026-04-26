# Phase 2 Scheduling

This folder is the starting point for phase 2 work focused on:

- availability form collection
- member submission flows
- service date display
- schedule generation and review

## Suggested Layout

- `backend/`: shared backend for all phases
- `frontend/phase_2/`: phase 2 member and admin page prototypes
- `docs/phase_2/`: phase-specific notes and planning

## Current Dependency Files

- `backend/requirements.txt`: runtime dependencies for the shared app
- `docs/phase_2/DEPENDENCIES.md`: short explanation of why each dependency exists

## Notes

- Phase 1 already includes working database models and baseline endpoints.
- The shared backend entry point now lives in the project root at `main.py`.
- Phase 2 can reuse the same database schema while adding better collection and scheduling workflows.
