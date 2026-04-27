from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from models import (
    AvailabilityEntry,
    Member,
    MemberRole,
    MonthlyForm,
    RescheduleRequest,
    Role,
    RoleConflict,
    Schedule,
    ServiceDate,
)


@dataclass
class WeekSlot:
    schedule: Schedule
    role: Role
    requested: bool
    preferred_candidate_ids: set[int]


@dataclass
class RescheduleWeekResult:
    week: int
    changed_schedule_ids: list[int]
    request_ids: list[int]
    note: str


@dataclass
class RescheduleResult:
    applied_weeks: list[RescheduleWeekResult]
    unresolved_weeks: list[RescheduleWeekResult]


def _has_conflict(role_id: int, assigned_roles_for_member: set[int], conflict_pairs: set[tuple[int, int]]) -> bool:
    for assigned_role_id in assigned_roles_for_member:
        if tuple(sorted((role_id, assigned_role_id))) in conflict_pairs:
            return True
    return False


def _service_period_worship_skip_weeks(db: Session, form_id: int) -> set[int]:
    service_dates = (
        db.query(ServiceDate)
        .filter(ServiceDate.form_id == form_id)
        .order_by(ServiceDate.friday_date)
        .all()
    )
    by_month: dict[tuple[int, int], list[ServiceDate]] = defaultdict(list)
    for service_date in service_dates:
        by_month[(service_date.friday_date.year, service_date.friday_date.month)].append(service_date)

    skipped_weeks: set[int] = set()
    for monthly_dates in by_month.values():
        for service_date in sorted(monthly_dates, key=lambda item: item.friday_date)[:2]:
            skipped_weeks.add(service_date.service_week)

    return skipped_weeks


def _role_group_is_valid(role: Role, week: int, assigned_members: list[Member], worship_leader_skip_weeks: set[int]) -> bool:
    if role.role_name == "Worship Leader" and week in worship_leader_skip_weeks:
        return not assigned_members

    if not assigned_members:
        return True

    if role.same_gender_required:
        genders = {member.member_gender for member in assigned_members}
        if len(genders) > 1:
            return False

    if role.role_name == "Worship Leader" and role.people_needed == 2 and len(assigned_members) == 2:
        senior_flags = {member.is_senior_for_pairing for member in assigned_members}
        return senior_flags == {True, False}

    if role.role_name == "Bible Study Leader" and role.people_needed == 2 and len(assigned_members) == 2:
        study_groups = {member.bible_study_group for member in assigned_members}
        return study_groups == {"group_a", "group_b"}

    if role.role_name == "Cleaner" and role.people_needed == 4 and len(assigned_members) == 4:
        genders = [member.member_gender for member in assigned_members]
        return genders.count("male") == 2 and genders.count("female") == 2

    return True


def _candidate_cost(
    slot: WeekSlot,
    member: Member,
    monthly_assignment_counts: dict[int, int],
    current_scope_assignments_by_week_member: dict[tuple[int, int], set[int]],
) -> int:
    cost = monthly_assignment_counts.get(member.member_id, 0)

    if slot.requested:
        if slot.preferred_candidate_ids:
            cost += 0 if member.member_id in slot.preferred_candidate_ids else 50
        else:
            cost += 20

        current_schedule_ids = current_scope_assignments_by_week_member.get(
            (slot.schedule.service_week, member.member_id),
            set(),
        )
        if current_schedule_ids and current_schedule_ids != {slot.schedule.schedule_id}:
            cost += 8
    else:
        cost += 0 if member.member_id == slot.schedule.member_id else 1000

    return cost


def list_replacement_candidates(db: Session, schedule: Schedule) -> list[dict]:
    monthly_assignment_counts = {
        member_id: count
        for member_id, count in db.query(Schedule.member_id, func.count(Schedule.schedule_id))
        .filter(Schedule.form_id == schedule.form_id)
        .group_by(Schedule.member_id)
        .all()
    }

    qualified_members = (
        db.query(Member)
        .join(MemberRole, MemberRole.member_id == Member.member_id)
        .filter(
            Member.is_active == True,
            MemberRole.role_id == schedule.role_id,
            MemberRole.is_current == True,
            Member.member_id != schedule.member_id,
        )
        .all()
    )

    available_member_ids = {
        row.member_id
        for row in db.query(AvailabilityEntry.member_id)
        .filter(
            AvailabilityEntry.form_id == schedule.form_id,
            AvailabilityEntry.service_week == schedule.service_week,
            AvailabilityEntry.is_available == True,
        )
        .all()
    }

    candidates = [
        member for member in qualified_members
        if member.member_id in available_member_ids
    ]
    candidates.sort(key=lambda member: (monthly_assignment_counts.get(member.member_id, 0), member.member_name))

    previous_week_member_ids = set()
    next_week_member_ids = set()
    if schedule.role.role_name == "Bible Study Leader":
        previous_week_member_ids = {
            member_id
            for member_id, in db.query(Schedule.member_id)
            .join(Role, Role.role_id == Schedule.role_id)
            .filter(
                Schedule.form_id == schedule.form_id,
                Schedule.service_week == schedule.service_week - 1,
                Role.role_name == "Bible Study Leader",
            )
            .all()
        }
        next_week_member_ids = {
            member_id
            for member_id, in db.query(Schedule.member_id)
            .join(Role, Role.role_id == Schedule.role_id)
            .filter(
                Schedule.form_id == schedule.form_id,
                Schedule.service_week == schedule.service_week + 1,
                Role.role_name == "Bible Study Leader",
            )
            .all()
        }

    return [
        {
            "member_id": member.member_id,
            "member_name": member.member_name,
            "member_gender": member.member_gender,
            "bible_study_group": member.bible_study_group,
            "is_senior_for_pairing": bool(member.is_senior_for_pairing),
            "served_previous_week_same_role": member.member_id in previous_week_member_ids,
            "served_next_week_same_role": member.member_id in next_week_member_ids,
            "monthly_assignment_count": monthly_assignment_counts.get(member.member_id, 0),
        }
        for member in candidates
    ]


def _violates_bible_study_gap(
    member_id: int,
    week: int,
    assignment_by_slot_index: dict[int, Member],
    slots: list[WeekSlot],
    fixed_bible_study_by_week: dict[int, set[int]],
) -> bool:
    for adjacent_week in (week - 1, week + 1):
        if member_id in fixed_bible_study_by_week.get(adjacent_week, set()):
            return True

        for assigned_slot_index, assigned_member in assignment_by_slot_index.items():
            other_slot = slots[assigned_slot_index]
            if (
                other_slot.role.role_name == "Bible Study Leader"
                and other_slot.schedule.service_week == adjacent_week
                and assigned_member.member_id == member_id
            ):
                return True

    return False


def _is_bible_study_role_pairing_valid(
    member: Member,
    week: int,
    assignment_by_slot_index: dict[int, Member],
    slots: list[WeekSlot],
    fixed_bible_study_by_week: dict[int, set[int]],
    enforce_gap_rule: bool,
) -> bool:
    if not enforce_gap_rule:
        return True

    return not _violates_bible_study_gap(
        member.member_id,
        week,
        assignment_by_slot_index,
        slots,
        fixed_bible_study_by_week,
    )


def _solve_week(
    db: Session,
    form_id: int,
    week: int,
    requests: list[RescheduleRequest],
) -> tuple[Optional[dict[int, Member]], str]:
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        return None, "Form not found."

    request_role_names = {request.role.role_name for request in requests if request.role}

    requested_week_schedules = (
        db.query(Schedule)
        .join(Role, Role.role_id == Schedule.role_id)
        .filter(Schedule.form_id == form_id, Schedule.service_week == week)
        .order_by(Schedule.role_id, Schedule.assignment_slot)
        .all()
    )
    if not requested_week_schedules:
        return None, "No schedules found for the affected week."

    schedules_by_id = {schedule.schedule_id: schedule for schedule in requested_week_schedules}
    if "Bible Study Leader" in request_role_names:
        bible_study_schedules = (
            db.query(Schedule)
            .join(Role, Role.role_id == Schedule.role_id)
            .filter(Schedule.form_id == form_id, Role.role_name == "Bible Study Leader")
            .order_by(Schedule.service_week, Schedule.assignment_slot)
            .all()
        )
        for schedule in bible_study_schedules:
            schedules_by_id.setdefault(schedule.schedule_id, schedule)

    schedules = sorted(
        schedules_by_id.values(),
        key=lambda schedule: (schedule.service_week, schedule.role_id, schedule.assignment_slot),
    )
    if not schedules:
        return None, "No schedules found for the affected week."

    worship_leader_skip_weeks = _service_period_worship_skip_weeks(db, form_id)

    roles = {role.role_id: role for role in db.query(Role).all()}
    role_by_name = {role.role_name: role for role in roles.values()}
    cleaning_leader_role = role_by_name.get("Cleaning Leader")
    cleaner_role = role_by_name.get("Cleaner")

    request_by_schedule_id = {request.schedule_id: request for request in requests}
    absent_member_ids_by_week: dict[int, set[int]] = defaultdict(set)
    for request in requests:
        absent_member_ids_by_week[request.service_week].add(request.original_member_id)

    weeks_in_scope = sorted({schedule.service_week for schedule in schedules})
    available_by_week: dict[int, set[int]] = defaultdict(set)
    for row in (
        db.query(AvailabilityEntry.member_id, AvailabilityEntry.service_week)
        .filter(
            AvailabilityEntry.form_id == form_id,
            AvailabilityEntry.service_week.in_(weeks_in_scope),
            AvailabilityEntry.is_available == True,
        )
        .all()
    ):
        available_by_week[row.service_week].add(row.member_id)

    active_members = db.query(Member).filter(Member.is_active == True).all()
    member_lookup = {member.member_id: member for member in active_members}

    qualified_by_week_role: dict[tuple[int, int], list[Member]] = defaultdict(list)
    qualifications = db.query(MemberRole).filter(MemberRole.is_current == True).all()
    for qualification in qualifications:
        member = member_lookup.get(qualification.member_id)
        if not member:
            continue
        for scope_week in weeks_in_scope:
            if member.member_id in absent_member_ids_by_week[scope_week]:
                continue
            if member.member_id in available_by_week[scope_week]:
                qualified_by_week_role[(scope_week, qualification.role_id)].append(member)

    cleaning_leader_qualified_ids = {
        member.member_id
        for member in qualified_by_week_role.get((week, cleaning_leader_role.role_id), [])
    } if cleaning_leader_role else set()

    monthly_assignment_counts = {
        member_id: count
        for member_id, count in db.query(Schedule.member_id, func.count(Schedule.schedule_id))
        .filter(Schedule.form_id == form_id)
        .group_by(Schedule.member_id)
        .all()
    }
    current_scope_assignments_by_week_member: dict[tuple[int, int], set[int]] = defaultdict(set)
    for schedule in schedules:
        current_scope_assignments_by_week_member[(schedule.service_week, schedule.member_id)].add(schedule.schedule_id)

    conflicts = db.query(RoleConflict).filter(RoleConflict.is_active == True).all()
    conflict_pairs = {tuple(sorted((conflict.role_id_1, conflict.role_id_2))) for conflict in conflicts}

    solve_schedule_ids = {schedule.schedule_id for schedule in schedules}
    fixed_roles_by_week_member: dict[tuple[int, int], set[int]] = defaultdict(set)
    fixed_bible_study_by_week: dict[int, set[int]] = defaultdict(set)
    fixed_scope_schedules = (
        db.query(Schedule)
        .join(Role, Role.role_id == Schedule.role_id)
        .filter(
            Schedule.form_id == form_id,
            Schedule.service_week.in_(weeks_in_scope),
        )
        .all()
    )
    for schedule in fixed_scope_schedules:
        if schedule.schedule_id in solve_schedule_ids:
            continue
        fixed_roles_by_week_member[(schedule.service_week, schedule.member_id)].add(schedule.role_id)
        if schedule.role.role_name == "Bible Study Leader":
            fixed_bible_study_by_week[schedule.service_week].add(schedule.member_id)

    slots: list[WeekSlot] = []
    for schedule in schedules:
        request = request_by_schedule_id.get(schedule.schedule_id)
        candidate_ids = {
            candidate.member_id
            for candidate in (request.candidates if request else [])
        }
        slots.append(
            WeekSlot(
                schedule=schedule,
                role=roles[schedule.role_id],
                requested=request is not None,
                preferred_candidate_ids=candidate_ids,
            )
        )

    candidate_members_by_slot: dict[int, list[Member]] = {}
    for index, slot in enumerate(slots):
        if slot.role.role_name == "Worship Leader" and slot.schedule.service_week in worship_leader_skip_weeks:
            candidate_members_by_slot[index] = []
            continue

        candidates = [
            member for member in qualified_by_week_role.get((slot.schedule.service_week, slot.role.role_id), [])
            if slot.requested or member.member_id == slot.schedule.member_id or member.member_id != slot.schedule.member_id
        ]
        if slot.role.role_name == "Cleaning Leader" and not candidates:
            candidates = [
                member for member in active_members
                if member.member_gender == "male"
                and member.member_id not in absent_member_ids_by_week[slot.schedule.service_week]
                and member.member_id in available_by_week[slot.schedule.service_week]
            ]
        if not slot.requested and slot.schedule.member_id not in {member.member_id for member in candidates}:
            current_member = db.query(Member).filter(Member.member_id == slot.schedule.member_id).first()
            if current_member:
                candidates.append(current_member)

        candidate_members_by_slot[index] = sorted(
            candidates,
            key=lambda member: (
                _candidate_cost(slot, member, monthly_assignment_counts, current_scope_assignments_by_week_member),
                member.member_name,
            ),
        )

    slot_order = sorted(
        range(len(slots)),
        key=lambda index: (
            0 if slots[index].requested else 1,
            0 if slots[index].role.role_name == "Bible Study Leader" else 1,
            0 if slots[index].role.same_gender_required else 1,
            len(candidate_members_by_slot[index]),
        ),
    )

    best_assignment: Optional[dict[int, Member]] = None
    best_cost: Optional[int] = None

    def cleaner_leader_fallback_is_valid(assignment_by_slot_index: dict[int, Member]) -> bool:
        if not cleaning_leader_role or not cleaner_role:
            return True

        cleaner_members_by_week: dict[int, list[Member]] = defaultdict(list)
        cleaning_leader_members_by_week: dict[int, list[Member]] = defaultdict(list)

        for index, member in assignment_by_slot_index.items():
            slot = slots[index]
            if slot.role.role_name == "Cleaner":
                cleaner_members_by_week[slot.schedule.service_week].append(member)
            elif slot.role.role_name == "Cleaning Leader":
                cleaning_leader_members_by_week[slot.schedule.service_week].append(member)

        for scoped_week, cleaning_leader_members in cleaning_leader_members_by_week.items():
            for member in cleaning_leader_members:
                if member.member_id in cleaning_leader_qualified_ids:
                    continue
                if member.member_gender != "male":
                    return False
                if member.member_id not in {cleaner.member_id for cleaner in cleaner_members_by_week.get(scoped_week, [])}:
                    return False

        return True

    def search(
        depth: int,
        assignment_by_slot_index: dict[int, Member],
        week_member_role_map: dict[tuple[int, int], set[int]],
        week_role_member_map: dict[tuple[int, int], list[Member]],
        used_members_by_week: dict[int, set[int]],
        total_cost: int,
        allow_multi_role: bool,
        enforce_bible_study_gap_rule: bool,
    ) -> None:
        nonlocal best_assignment, best_cost

        if best_cost is not None and total_cost >= best_cost:
            return

        if depth == len(slot_order):
            if not cleaner_leader_fallback_is_valid(assignment_by_slot_index):
                return
            best_assignment = dict(assignment_by_slot_index)
            best_cost = total_cost
            return

        slot_index = slot_order[depth]
        slot = slots[slot_index]
        week = slot.schedule.service_week

        if slot.role.role_name == "Worship Leader" and week in worship_leader_skip_weeks:
            return

        for member in candidate_members_by_slot[slot_index]:
            if slot.requested and member.member_id == slot.schedule.member_id:
                continue

            if member.member_id in {assigned_member.member_id for assigned_member in week_role_member_map[(week, slot.role.role_id)]}:
                continue

            if not allow_multi_role and member.member_id in used_members_by_week[week]:
                continue

            assigned_roles_for_member = set(week_member_role_map[(week, member.member_id)])
            assigned_roles_for_member.update(fixed_roles_by_week_member[(week, member.member_id)])

            if allow_multi_role and _has_conflict(slot.role.role_id, assigned_roles_for_member, conflict_pairs):
                continue
            if not allow_multi_role and fixed_roles_by_week_member[(week, member.member_id)]:
                continue

            new_role_group = week_role_member_map[(week, slot.role.role_id)] + [member]
            if not _role_group_is_valid(slot.role, week, new_role_group, worship_leader_skip_weeks):
                continue

            if (
                slot.role.role_name == "Bible Study Leader"
                and not _is_bible_study_role_pairing_valid(
                    member,
                    week,
                    assignment_by_slot_index,
                    slots,
                    fixed_bible_study_by_week,
                    enforce_gap_rule=enforce_bible_study_gap_rule,
                )
            ):
                continue

            assignment_by_slot_index[slot_index] = member
            week_role_member_map[(week, slot.role.role_id)].append(member)
            week_member_role_map[(week, member.member_id)].add(slot.role.role_id)
            added_to_used = False
            if member.member_id not in used_members_by_week[week]:
                used_members_by_week[week].add(member.member_id)
                added_to_used = True

            incremental_cost = _candidate_cost(
                slot,
                member,
                monthly_assignment_counts,
                current_scope_assignments_by_week_member,
            )
            if slot.role.role_name == "Cleaner" and member.member_id in cleaning_leader_qualified_ids:
                incremental_cost -= 2
            if slot.role.role_name == "Cleaning Leader" and member.member_id not in cleaning_leader_qualified_ids:
                incremental_cost += 25
            search(
                depth + 1,
                assignment_by_slot_index,
                week_member_role_map,
                week_role_member_map,
                used_members_by_week,
                total_cost + incremental_cost,
                allow_multi_role,
                enforce_bible_study_gap_rule,
            )

            if added_to_used:
                used_members_by_week[week].remove(member.member_id)
            week_member_role_map[(week, member.member_id)].remove(slot.role.role_id)
            week_role_member_map[(week, slot.role.role_id)].pop()
            assignment_by_slot_index.pop(slot_index, None)

    for allow_multi_role, enforce_bible_study_gap_rule in (
        (False, True),
        (False, False),
        (True, True),
        (True, False),
    ):
        search(
            depth=0,
            assignment_by_slot_index={},
            week_member_role_map=defaultdict(set),
            week_role_member_map=defaultdict(list),
            used_members_by_week=defaultdict(set),
            total_cost=0,
            allow_multi_role=allow_multi_role,
            enforce_bible_study_gap_rule=enforce_bible_study_gap_rule,
        )
        if best_assignment is not None:
            break

    if best_assignment is None:
        return None, "No valid replacement chain was found while keeping Bible Study Leader as one Group A leader plus one Group B leader."

    return {
        slots[index].schedule.schedule_id: member
        for index, member in best_assignment.items()
    }, "Applied minimal-change reschedule while prioritizing one Group A and one Group B Bible Study Leader."


def process_open_reschedule_requests(db: Session, form_id: Optional[int] = None) -> RescheduleResult:
    query = (
        db.query(RescheduleRequest)
        .join(
            ServiceDate,
            and_(
                ServiceDate.form_id == RescheduleRequest.form_id,
                ServiceDate.service_week == RescheduleRequest.service_week,
            ),
        )
        .filter(
            RescheduleRequest.status == 'open',
            ServiceDate.friday_date > date.today(),
        )
    )
    if form_id is not None:
        query = query.filter(RescheduleRequest.form_id == form_id)

    requests = query.order_by(RescheduleRequest.submitted_at, RescheduleRequest.request_id).all()
    requests_by_week: dict[tuple[int, int], list[RescheduleRequest]] = defaultdict(list)
    for request in requests:
        requests_by_week[(request.form_id, request.service_week)].append(request)

    applied_weeks: list[RescheduleWeekResult] = []
    unresolved_weeks: list[RescheduleWeekResult] = []

    for (week_form_id, week), week_requests in sorted(requests_by_week.items()):
        assignment_by_schedule_id, note = _solve_week(db, week_form_id, week, week_requests)
        if assignment_by_schedule_id is None:
            unresolved_weeks.append(
                RescheduleWeekResult(
                    week=week,
                    changed_schedule_ids=[],
                    request_ids=[request.request_id for request in week_requests],
                    note=note,
                )
            )
            continue

        changed_schedule_ids: list[int] = []
        for schedule_id, member in assignment_by_schedule_id.items():
            schedule = db.query(Schedule).filter(Schedule.schedule_id == schedule_id).first()
            if schedule and schedule.member_id != member.member_id:
                changed_schedule_ids.append(schedule_id)
                original_member_id = schedule.member_id
                schedule.member_id = member.member_id
                schedule.notes = (
                    f"Rescheduled on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}; "
                    f"replaced member {original_member_id} with {member.member_id}"
                )

        for request in week_requests:
            request.status = 'applied'
            request.processed_at = datetime.utcnow()
            request.processed_note = note

        applied_weeks.append(
            RescheduleWeekResult(
                week=week,
                changed_schedule_ids=changed_schedule_ids,
                request_ids=[request.request_id for request in week_requests],
                note=note,
            )
        )

    db.commit()

    return RescheduleResult(
        applied_weeks=applied_weeks,
        unresolved_weeks=unresolved_weeks,
    )
