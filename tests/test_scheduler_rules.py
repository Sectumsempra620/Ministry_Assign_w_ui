from datetime import date

from backend.scheduler import generate_schedule
from models import AvailabilityEntry, Member, MemberRole, MonthlyForm, Role, ServiceDate


def test_generate_schedule_skips_worship_leader_for_first_two_fridays_of_each_month(app_module, db_session):
    worship_role = Role(
        role_name="Worship Leader",
        people_needed=2,
        same_gender_required=True,
    )
    db_session.add(worship_role)
    db_session.commit()
    db_session.refresh(worship_role)

    member_one = Member(
        member_name="Leader One",
        member_gender="female",
        email="leader.one@example.com",
        is_active=True,
        is_senior_for_pairing=True,
    )
    member_two = Member(
        member_name="Leader Two",
        member_gender="female",
        email="leader.two@example.com",
        is_active=True,
        is_senior_for_pairing=False,
    )
    db_session.add_all([member_one, member_two])
    db_session.commit()
    db_session.refresh(member_one)
    db_session.refresh(member_two)

    form = MonthlyForm(
        form_month=date(2026, 6, 1),
        service_weeks=8,
        status="open",
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    db_session.add_all(
        [
            MemberRole(member_id=member_one.member_id, role_id=worship_role.role_id, is_current=True),
            MemberRole(member_id=member_two.member_id, role_id=worship_role.role_id, is_current=True),
            ServiceDate(form_id=form.form_id, service_week=1, friday_date=date(2026, 6, 5)),
            ServiceDate(form_id=form.form_id, service_week=2, friday_date=date(2026, 6, 12)),
            ServiceDate(form_id=form.form_id, service_week=3, friday_date=date(2026, 6, 19)),
            ServiceDate(form_id=form.form_id, service_week=4, friday_date=date(2026, 6, 26)),
            ServiceDate(form_id=form.form_id, service_week=5, friday_date=date(2026, 7, 3)),
            ServiceDate(form_id=form.form_id, service_week=6, friday_date=date(2026, 7, 10)),
            ServiceDate(form_id=form.form_id, service_week=7, friday_date=date(2026, 7, 17)),
            ServiceDate(form_id=form.form_id, service_week=8, friday_date=date(2026, 7, 24)),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=2, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=2, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=3, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=3, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=4, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=4, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=5, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=5, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=6, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=6, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=7, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=7, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_one.member_id, service_week=8, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=member_two.member_id, service_week=8, is_available=True),
        ]
    )
    db_session.commit()

    result = generate_schedule(form_id=form.form_id, db=db_session, replace_existing=False)

    worship_assignments = [
        assignment for assignment in result.created if assignment.role_id == worship_role.role_id
    ]

    assert {assignment.service_week for assignment in worship_assignments} == {3, 4, 7, 8}
    assert all(assignment.service_week not in {1, 2, 5, 6} for assignment in worship_assignments)


def test_generate_schedule_assigns_cleaners_as_two_men_two_women_with_cleaning_leader_fallback(app_module, db_session):
    cleaning_leader_role = Role(
        role_name="Cleaning Leader",
        people_needed=1,
        same_gender_required=False,
    )
    cleaner_role = Role(
        role_name="Cleaner",
        people_needed=4,
        same_gender_required=False,
    )
    db_session.add_all([cleaning_leader_role, cleaner_role])
    db_session.commit()
    db_session.refresh(cleaning_leader_role)
    db_session.refresh(cleaner_role)

    members = [
        Member(member_name="Leader Qualified Brother", member_gender="male", email="leaderq@example.com", is_active=True),
        Member(member_name="Brother Two", member_gender="male", email="bro2@example.com", is_active=True),
        Member(member_name="Sister One", member_gender="female", email="sis1@example.com", is_active=True),
        Member(member_name="Sister Two", member_gender="female", email="sis2@example.com", is_active=True),
    ]
    db_session.add_all(members)
    db_session.commit()
    for member in members:
        db_session.refresh(member)

    form = MonthlyForm(
        form_month=date(2026, 6, 1),
        service_weeks=1,
        status="open",
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    db_session.add(ServiceDate(form_id=form.form_id, service_week=1, friday_date=date(2026, 6, 5)))
    db_session.add_all(
        [
            MemberRole(member_id=members[0].member_id, role_id=cleaning_leader_role.role_id, is_current=True),
            MemberRole(member_id=members[0].member_id, role_id=cleaner_role.role_id, is_current=True),
            MemberRole(member_id=members[1].member_id, role_id=cleaner_role.role_id, is_current=True),
            MemberRole(member_id=members[2].member_id, role_id=cleaner_role.role_id, is_current=True),
            MemberRole(member_id=members[3].member_id, role_id=cleaner_role.role_id, is_current=True),
        ]
    )
    db_session.add_all(
        [
            AvailabilityEntry(form_id=form.form_id, member_id=members[0].member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=members[1].member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=members[2].member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=members[3].member_id, service_week=1, is_available=True),
        ]
    )
    db_session.commit()

    result = generate_schedule(form_id=form.form_id, db=db_session, replace_existing=False)

    cleaner_assignments = [assignment for assignment in result.created if assignment.role_id == cleaner_role.role_id]
    assert len(cleaner_assignments) == 4

    assigned_cleaners = [member for member in members if member.member_id in {assignment.member_id for assignment in cleaner_assignments}]
    genders = [member.member_gender for member in assigned_cleaners]
    assert genders.count("male") == 2
    assert genders.count("female") == 2
    assert members[0].member_id in {assignment.member_id for assignment in cleaner_assignments}

    cleaning_leader_assignments = [assignment for assignment in result.created if assignment.role_id == cleaning_leader_role.role_id]
    assert len(cleaning_leader_assignments) == 1
    assert cleaning_leader_assignments[0].member_id == members[0].member_id


def test_generate_schedule_promotes_male_cleaner_when_no_cleaning_leader_is_available(app_module, db_session):
    cleaning_leader_role = Role(
        role_name="Cleaning Leader",
        people_needed=1,
        same_gender_required=False,
    )
    cleaner_role = Role(
        role_name="Cleaner",
        people_needed=4,
        same_gender_required=False,
    )
    db_session.add_all([cleaning_leader_role, cleaner_role])
    db_session.commit()
    db_session.refresh(cleaning_leader_role)
    db_session.refresh(cleaner_role)

    members = [
        Member(member_name="Brother One", member_gender="male", email="cbro1@example.com", is_active=True),
        Member(member_name="Brother Two", member_gender="male", email="cbro2@example.com", is_active=True),
        Member(member_name="Sister One", member_gender="female", email="csis1@example.com", is_active=True),
        Member(member_name="Sister Two", member_gender="female", email="csis2@example.com", is_active=True),
    ]
    db_session.add_all(members)
    db_session.commit()
    for member in members:
        db_session.refresh(member)

    form = MonthlyForm(
        form_month=date(2026, 6, 1),
        service_weeks=1,
        status="open",
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)

    db_session.add(ServiceDate(form_id=form.form_id, service_week=1, friday_date=date(2026, 6, 5)))
    db_session.add_all(
        [
            MemberRole(member_id=members[0].member_id, role_id=cleaner_role.role_id, is_current=True),
            MemberRole(member_id=members[1].member_id, role_id=cleaner_role.role_id, is_current=True),
            MemberRole(member_id=members[2].member_id, role_id=cleaner_role.role_id, is_current=True),
            MemberRole(member_id=members[3].member_id, role_id=cleaner_role.role_id, is_current=True),
        ]
    )
    db_session.add_all(
        [
            AvailabilityEntry(form_id=form.form_id, member_id=members[0].member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=members[1].member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=members[2].member_id, service_week=1, is_available=True),
            AvailabilityEntry(form_id=form.form_id, member_id=members[3].member_id, service_week=1, is_available=True),
        ]
    )
    db_session.commit()

    result = generate_schedule(form_id=form.form_id, db=db_session, replace_existing=False)

    cleaner_assignments = [assignment for assignment in result.created if assignment.role_id == cleaner_role.role_id]
    cleaning_leader_assignments = [assignment for assignment in result.created if assignment.role_id == cleaning_leader_role.role_id]

    assert len(cleaner_assignments) == 4
    assert len(cleaning_leader_assignments) == 1
    assert cleaning_leader_assignments[0].member_id in {members[0].member_id, members[1].member_id}
