# API Reference

This file is the main API endpoint reference for the project.

The backend serves interactive docs at:

- `http://localhost:8000/docs`

## Core Endpoints

### Members

- `POST /api/v1/members`
- `GET /api/v1/members`
- `GET /api/v1/members/{member_id}`
- `PUT /api/v1/members/{member_id}`
- `DELETE /api/v1/members/{member_id}`

### Roles

- `GET /api/v1/roles`
- `POST /api/v1/member-roles`

### Monthly forms

- `POST /api/v1/forms`
- `GET /api/v1/forms`
- `GET /api/v1/forms/{form_id}`
- `PUT /api/v1/forms/{form_id}/status`

### Service dates

- `GET /api/v1/forms/{form_id}/service-dates`
- `POST /api/v1/service-dates`

### Availability

- `POST /api/v1/availability?form_id=1&member_id=5`
- `GET /api/v1/forms/{form_id}/availability`

### Schedules

- `POST /api/v1/schedules`
- `GET /api/v1/schedules`
- `GET /api/v1/forms/{form_id}/schedules`

### Reporting

- `GET /api/v1/forms/{form_id}/report`

### Health

- `GET /health`

## Example Requests

### Create a member

```http
POST /api/v1/members
Content-Type: application/json

{
  "member_name": "Test Member",
  "member_gender": "female",
  "email": "test@church.com"
}
```

### Open a form

```http
PUT /api/v1/forms/1/status
Content-Type: application/json

{
  "status": "open"
}
```

### Submit availability

```http
POST /api/v1/availability?form_id=1&member_id=5
Content-Type: application/json

{
  "week_1": true,
  "week_2": false,
  "week_3": true,
  "week_4": true
}
```

### Create a schedule assignment

```http
POST /api/v1/schedules
Content-Type: application/json

{
  "form_id": 1,
  "service_week": 1,
  "role_id": 2,
  "member_id": 3
}
```

## Validation Rules

Important checks in the backend include:

- member email uniqueness
- one form per month
- valid form status transitions by allowed values
- member must be qualified for a role before assignment
- member must be available for the selected week
- one role assignment per week, per form

## Best Way To Explore

Use `http://localhost:8000/docs` for the live OpenAPI UI. It is more complete and current than any handwritten summary file.
