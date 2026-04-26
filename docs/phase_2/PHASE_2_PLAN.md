# Phase 2 Plan

## Goal

Expand phase 1 into a workflow where:

1. an admin opens a monthly form
2. members submit weekly availability against real service dates
3. admins review participation and build the final schedule

## Immediate Deliverables

- phase 2 module and page scaffolding
- dedicated availability form page
- API contract for loading a member-specific form
- API contract for submitting availability

## Recommended Next Tasks

1. Move shared SQLAlchemy models into a reusable module so phase 1 and phase 2 do not drift.
2. Add member lookup by email token or invite link instead of raw `member_id` query params.
3. Add admin availability dashboard views grouped by week and role coverage.
4. Add scheduling helpers that suggest qualified and available members.
5. Add tests for:
   - open vs closed form submission
   - inactive member rejection
   - partial week submission
   - existing entry updates

## Shared Backend Direction

- keep one shared app entry point in `main.py`
- keep shared ORM and schema models in `models.py`
- add new phase 2 endpoints into the shared backend instead of creating a second deployed app
