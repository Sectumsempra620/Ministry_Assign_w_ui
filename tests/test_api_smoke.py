from datetime import date


def test_health_endpoint_returns_healthy_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"
    assert "timestamp" in body


def test_root_endpoint_exposes_basic_links(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["documentation"] == "/docs"
    assert body["health"] == "/health"
    assert body["version"] == "1.0.0"


def test_forms_and_service_dates_round_trip(client):
    form_response = client.post(
        "/api/v1/forms",
        json={
            "form_month": date(2026, 6, 1).isoformat(),
            "service_weeks": 13,
            "submission_deadline": date(2026, 5, 29).isoformat(),
            "notes": "Summer service period",
        },
    )

    assert form_response.status_code == 201
    form = form_response.json()
    assert form["service_weeks"] == 13

    service_date_response = client.post(
        "/api/v1/service-dates",
        json={
            "form_id": form["form_id"],
            "service_week": 1,
            "friday_date": date(2026, 6, 5).isoformat(),
            "is_holiday": False,
            "notes": "Week 1 Friday",
        },
    )

    assert service_date_response.status_code == 201

    forms_response = client.get("/api/v1/forms")
    assert forms_response.status_code == 200
    assert len(forms_response.json()) == 1

    dates_response = client.get(f"/api/v1/forms/{form['form_id']}/service-dates")
    assert dates_response.status_code == 200
    dates = dates_response.json()
    assert len(dates) == 1
    assert dates[0]["service_week"] == 1
    assert dates[0]["friday_date"] == "2026-06-05"
