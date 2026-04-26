# Phase 2 Dependency Notes

## Runtime Dependencies

- `fastapi`: API layer for member availability submission and admin scheduling actions
- `uvicorn[standard]`: local and server ASGI runtime
- `sqlalchemy`: database access for forms, availability, roles, and schedules
- `pymysql`: MySQL driver for the existing RDS database
- `cryptography`: secure support required by MySQL client stacks in many deployments
- `pydantic`: request and response validation
- `pydantic-settings`: structured settings loading if phase 2 moves config into classes
- `python-dotenv`: load environment variables from `.env`
- `python-multipart`: support form posts if member submissions use HTML forms
- `jinja2`: useful if phase 2 introduces server-rendered availability pages or email templates
- `email-validator`: clean validation for member email-based workflows
- `httpx`: useful for API tests, internal service calls, or notification integrations

## Development Dependencies

- `pytest`: test runner
- `pytest-asyncio`: async test support for FastAPI work
- `pytest-cov`: coverage reporting
- `ruff`: linting and formatting support

## Why This Starts Close To Phase 1

Phase 1 already has most of the core backend stack in place. These files keep the same foundation so phase 2 can focus on feature work instead of platform churn.
