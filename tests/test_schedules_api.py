from datetime import date

from models import AvailabilityEntry, Member, MemberRole, MonthlyForm, Role, ServiceDate


def test_form_schedule_endpoint_returns_assignments_with_names(client, db_session):
    role = Role(role_name="Cleaner", people_needed=1, same_gender_required=False)
    member = Member(
        member_name="Schedule Tester",
        member_gender="male",
        email="schedule.tester@example.com",
        is_active=True,
    )
    form = MonthlyForm(
        form_month=date(2026, 6, 1),
        service_weeks=13,
        status="open",
    )
    db_session.add_all([role, member, form])
    db_session.commit()
    db_session.refresh(role)
    db_session.refresh(member)
    db_session.refresh(form)

    service_date = ServiceDate(
        form_id=form.form_id,
        service_week=1,
        friday_date=date(2026, 6, 5),
    )
    member_role = MemberRole(
        member_id=member.member_id,
        role_id=role.role_id,
        is_current=True,
    )
    availability = AvailabilityEntry(
        form_id=form.form_id,
        member_id=member.member_id,
        service_week=1,
        is_available=True,
    )
    db_session.add_all([service_date, member_role, availability])
    db_session.commit()

    create_response = client.post(
        "/api/v1/schedules",
        json={
            "form_id": form.form_id,
            "service_week": 1,
            "role_id": role.role_id,
            "assignment_slot": 1,
            "member_id": member.member_id,
            "notes": "Opening week assignment",
        },
    )

    assert create_response.status_code == 201
    created_schedule = create_response.json()
    assert created_schedule["role_name"] == "Cleaner"
    assert created_schedule["member_name"] == "Schedule Tester"

    schedules_response = client.get(f"/api/v1/forms/{form.form_id}/schedules")
    assert schedules_response.status_code == 200
    schedules = schedules_response.json()
    assert len(schedules) == 1
    assert schedules[0]["notes"] == "Opening week assignment"


def test_generate_service_dates_creates_all_fridays_for_period(client, db_session):
    form = MonthlyForm(
        form_month=date(2026, 6, 1),
        service_weeks=0,
        status="draft",
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    response = client.post(f"/api/v1/forms/{form.form_id}/generate-service-dates")

    assert response.status_code == 201
    service_dates = response.json()
    assert len(service_dates) == 13
    assert service_dates[0]["service_week"] == 1
    assert service_dates[0]["friday_date"] == "2026-06-05"
    assert service_dates[-1]["service_week"] == 13
    assert service_dates[-1]["friday_date"] == "2026-08-28"

    db_session.expire_all()
    stored_form = db_session.query(MonthlyForm).filter(MonthlyForm.form_id == form.form_id).first()
    assert stored_form.service_weeks == 13
