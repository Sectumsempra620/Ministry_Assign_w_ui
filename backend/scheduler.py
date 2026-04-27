from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Optional

from sqlalchemy.orm import Session

from models import AvailabilityEntry, Member, MemberRole, MonthlyForm, Role, RoleConflict, Schedule, ServiceDate


@dataclass
class SchedulingGap:
    week: int
    role_id: int
    role_name: str
    required_slots: int
    filled_slots: int
    reason: str


@dataclass
class SchedulingResult:
    created: list[Schedule]
    gaps: list[SchedulingGap]


def _worship_leader_skip_weeks(service_dates: list[ServiceDate]) -> set[int]:
    by_month: dict[tuple[int, int], list[ServiceDate]] = defaultdict(list)
    for service_date in service_dates:
        by_month[(service_date.friday_date.year, service_date.friday_date.month)].append(service_date)

    skipped_weeks: set[int] = set()
    for monthly_dates in by_month.values():
        for service_date in sorted(monthly_dates, key=lambda item: item.friday_date)[:2]:
            skipped_weeks.add(service_date.service_week)

    return skipped_weeks


def _candidate_sort_key(
    member: Member,
    total_assignments: dict[int, int],
    week_assignments: dict[int, set[int]],
    role_history: dict[tuple[int, int], int],
    role_id: int,
) -> tuple[int, int, int, str]:
    return (
        total_assignments[member.member_id],
        len(week_assignments[member.member_id]),
        role_history[(member.member_id, role_id)],
        member.member_name,
    )


def _has_conflict(member_id: int, role_id: int, assigned_roles_for_member: set[int], conflict_pairs: set[tuple[int, int]]) -> bool:
    for assigned_role_id in assigned_roles_for_member:
        pair = tuple(sorted((role_id, assigned_role_id)))
        if pair in conflict_pairs:
            return True
    return False


def _eligible_candidates(
    role: Role,
    candidates: list[Member],
    week: int,
    total_assignments: dict[int, int],
    week_assignments: dict[int, set[int]],
    role_history: dict[tuple[int, int], int],
    assigned_roles_by_member: dict[int, set[int]],
    conflict_pairs: set[tuple[int, int]],
    require_unused_this_week: bool,
) -> list[Member]:
    eligible = []
    for member in candidates:
        if require_unused_this_week and week in week_assignments[member.member_id]:
            continue
        if _has_conflict(member.member_id, role.role_id, assigned_roles_by_member[member.member_id], conflict_pairs):
            continue
        eligible.append(member)

    eligible.sort(
        key=lambda member: _candidate_sort_key(
            member,
            total_assignments,
            week_assignments,
            role_history,
            role.role_id,
        )
    )
    return eligible


def _assign_standard_role(
    role: Role,
    candidates: list[Member],
    week: int,
    form_id: int,
    total_assignments: dict[int, int],
    week_assignments: dict[int, set[int]],
    role_history: dict[tuple[int, int], int],
    assigned_roles_by_member: dict[int, set[int]],
    conflict_pairs: set[tuple[int, int]],
    blocked_member_ids: Optional[set[int]] = None,
) -> tuple[list[Schedule], Optional[SchedulingGap]]:
    chosen: list[Member] = []
    blocked_member_ids = blocked_member_ids or set()

    for require_unused_this_week in (True, False):
        eligible = _eligible_candidates(
            role,
            candidates,
            week,
            total_assignments,
            week_assignments,
            role_history,
            assigned_roles_by_member,
            conflict_pairs,
            require_unused_this_week=require_unused_this_week,
        )
        for member in eligible:
            if member.member_id in {item.member_id for item in chosen}:
                continue
            if member.member_id in blocked_member_ids:
                continue
            chosen.append(member)
            if len(chosen) == role.people_needed:
                break
        if len(chosen) == role.people_needed:
            break

    if len(chosen) < role.people_needed:
        return [], SchedulingGap(
            week=week,
            role_id=role.role_id,
            role_name=role.role_name,
            required_slots=role.people_needed,
            filled_slots=len(chosen),
            reason="Not enough qualified and available members under current conflict rules.",
        )

    assignments = []
    for slot, member in enumerate(chosen, start=1):
        assignments.append(
            Schedule(
                form_id=form_id,
                service_week=week,
                role_id=role.role_id,
                assignment_slot=slot,
                member_id=member.member_id,
                notes="Auto-generated schedule",
            )
        )
        total_assignments[member.member_id] += 1
        week_assignments[member.member_id].add(week)
        role_history[(member.member_id, role.role_id)] += 1
        assigned_roles_by_member[member.member_id].add(role.role_id)

    return assignments, None


def _assign_bible_study_role(
    role: Role,
    candidates: list[Member],
    week: int,
    form_id: int,
    total_assignments: dict[int, int],
    week_assignments: dict[int, set[int]],
    role_history: dict[tuple[int, int], int],
    assigned_roles_by_member: dict[int, set[int]],
    conflict_pairs: set[tuple[int, int]],
    blocked_member_ids: Optional[set[int]] = None,
) -> tuple[list[Schedule], Optional[SchedulingGap]]:
    blocked_member_ids = blocked_member_ids or set()
    grouped_candidates: dict[str, list[Member]] = defaultdict(list)
    for member in candidates:
        if member.bible_study_group in {"group_a", "group_b"}:
            grouped_candidates[member.bible_study_group].append(member)

    best_pair: Optional[list[Member]] = None

    for require_unused_this_week in (True, False):
        eligible_by_group: dict[str, list[Member]] = {}
        for group_name in ("group_a", "group_b"):
            eligible_by_group[group_name] = _eligible_candidates(
                role,
                grouped_candidates.get(group_name, []),
                week,
                total_assignments,
                week_assignments,
                role_history,
                assigned_roles_by_member,
                conflict_pairs,
                require_unused_this_week=require_unused_this_week,
            )

        for allow_consecutive in (False, True):
            group_a_candidates = [
                member for member in eligible_by_group["group_a"]
                if allow_consecutive or member.member_id not in blocked_member_ids
            ]
            group_b_candidates = [
                member for member in eligible_by_group["group_b"]
                if allow_consecutive or member.member_id not in blocked_member_ids
            ]

            possible_pairs = [
                [group_a_member, group_b_member]
                for group_a_member in group_a_candidates
                for group_b_member in group_b_candidates
                if group_a_member.member_id != group_b_member.member_id
            ]

            if possible_pairs:
                best_pair = min(
                    possible_pairs,
                    key=lambda pair: (
                        sum(total_assignments[member.member_id] for member in pair),
                        sum(role_history[(member.member_id, role.role_id)] for member in pair),
                        pair[0].member_name,
                        pair[1].member_name,
                    ),
                )
                break

        if best_pair:
            break

    if not best_pair or len(best_pair) < role.people_needed:
        return [], SchedulingGap(
            week=week,
            role_id=role.role_id,
            role_name=role.role_name,
            required_slots=role.people_needed,
            filled_slots=0,
            reason="Not enough qualified and available members to assign one Group A leader and one Group B leader.",
        )

    assignments = []
    for slot, member in enumerate(best_pair, start=1):
        assignments.append(
            Schedule(
                form_id=form_id,
                service_week=week,
                role_id=role.role_id,
                assignment_slot=slot,
                member_id=member.member_id,
                notes="Auto-generated schedule",
            )
        )
        total_assignments[member.member_id] += 1
        week_assignments[member.member_id].add(week)
        role_history[(member.member_id, role.role_id)] += 1
        assigned_roles_by_member[member.member_id].add(role.role_id)

    return assignments, None


def _assign_cleaner_role(
    role: Role,
    candidates: list[Member],
    week: int,
    form_id: int,
    total_assignments: dict[int, int],
    week_assignments: dict[int, set[int]],
    role_history: dict[tuple[int, int], int],
    assigned_roles_by_member: dict[int, set[int]],
    conflict_pairs: set[tuple[int, int]],
    cleaning_leader_qualified_ids: set[int],
) -> tuple[list[Schedule], Optional[SchedulingGap]]:
    male_candidates = [member for member in candidates if member.member_gender == "male"]
    female_candidates = [member for member in candidates if member.member_gender == "female"]

    best_group: Optional[list[Member]] = None

    for require_unused_this_week in (True, False):
        eligible_males = _eligible_candidates(
            role,
            male_candidates,
            week,
            total_assignments,
            week_assignments,
            role_history,
            assigned_roles_by_member,
            conflict_pairs,
            require_unused_this_week=require_unused_this_week,
        )
        eligible_females = _eligible_candidates(
            role,
            female_candidates,
            week,
            total_assignments,
            week_assignments,
            role_history,
            assigned_roles_by_member,
            conflict_pairs,
            require_unused_this_week=require_unused_this_week,
        )

        if len(eligible_males) < 2 or len(eligible_females) < 2:
            continue

        possible_groups: list[list[Member]] = []
        for male_pair in combinations(eligible_males, 2):
            for female_pair in combinations(eligible_females, 2):
                possible_groups.append([*male_pair, *female_pair])

        if possible_groups:
            best_group = min(
                possible_groups,
                key=lambda group: (
                    0 if any(member.member_id in cleaning_leader_qualified_ids for member in group) else 1,
                    sum(total_assignments[member.member_id] for member in group),
                    sum(role_history[(member.member_id, role.role_id)] for member in group),
                    sorted(member.member_name for member in group),
                ),
            )
            break

    if not best_group or len(best_group) < role.people_needed:
        return [], SchedulingGap(
            week=week,
            role_id=role.role_id,
            role_name=role.role_name,
            required_slots=role.people_needed,
            filled_slots=0,
            reason="Not enough qualified and available members to assign two male and two female cleaners.",
        )

    assignments = []
    for slot, member in enumerate(best_group, start=1):
        assignments.append(
            Schedule(
                form_id=form_id,
                service_week=week,
                role_id=role.role_id,
                assignment_slot=slot,
                member_id=member.member_id,
                notes="Auto-generated schedule",
            )
        )
        total_assignments[member.member_id] += 1
        week_assignments[member.member_id].add(week)
        role_history[(member.member_id, role.role_id)] += 1
        assigned_roles_by_member[member.member_id].add(role.role_id)

    return assignments, None


def _assign_same_gender_role(
    role: Role,
    candidates: list[Member],
    week: int,
    form_id: int,
    total_assignments: dict[int, int],
    week_assignments: dict[int, set[int]],
    role_history: dict[tuple[int, int], int],
    assigned_roles_by_member: dict[int, set[int]],
    conflict_pairs: set[tuple[int, int]],
) -> tuple[list[Schedule], Optional[SchedulingGap]]:
    grouped: dict[str, list[Member]] = defaultdict(list)
    for member in candidates:
        if member.member_gender:
            grouped[member.member_gender].append(member)

    best_group: Optional[list[Member]] = None

    for require_unused_this_week in (True, False):
        possible_groups: list[list[Member]] = []
        for members in grouped.values():
            eligible = _eligible_candidates(
                role,
                members,
                week,
                total_assignments,
                week_assignments,
                role_history,
                assigned_roles_by_member,
                conflict_pairs,
                require_unused_this_week=require_unused_this_week,
            )
            if role.role_name == "Worship Leader" and role.people_needed == 2:
                senior_members = [member for member in eligible if member.is_senior_for_pairing]
                younger_members = [member for member in eligible if not member.is_senior_for_pairing]
                if senior_members and younger_members:
                    possible_groups.append([senior_members[0], younger_members[0]])
            elif len(eligible) >= role.people_needed:
                possible_groups.append(eligible[: role.people_needed])

        if possible_groups:
            best_group = min(
                possible_groups,
                key=lambda group: (
                    sum(total_assignments[member.member_id] for member in group),
                    sum(role_history[(member.member_id, role.role_id)] for member in group),
                    group[0].member_gender or "",
                ),
            )
            break

    if not best_group or len(best_group) < role.people_needed:
        return [], SchedulingGap(
            week=week,
            role_id=role.role_id,
            role_name=role.role_name,
            required_slots=role.people_needed,
            filled_slots=0,
            reason=(
                "Not enough same-gender qualified and available members with one senior and one younger pairing partner."
                if role.role_name == "Worship Leader" and role.people_needed == 2
                else "Not enough same-gender qualified and available members."
            ),
        )

    assignments = []
    for slot, member in enumerate(best_group, start=1):
        assignments.append(
            Schedule(
                form_id=form_id,
                service_week=week,
                role_id=role.role_id,
                assignment_slot=slot,
                member_id=member.member_id,
                notes="Auto-generated schedule",
            )
        )
        total_assignments[member.member_id] += 1
        week_assignments[member.member_id].add(week)
        role_history[(member.member_id, role.role_id)] += 1
        assigned_roles_by_member[member.member_id].add(role.role_id)

    return assignments, None


def generate_schedule(form_id: int, db: Session, replace_existing: bool = False) -> SchedulingResult:
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise ValueError("Form not found")

    service_dates = db.query(ServiceDate).filter(ServiceDate.form_id == form_id).order_by(ServiceDate.service_week).all()
    if not service_dates:
        raise ValueError("Service dates are not configured for this form")

    if replace_existing:
        db.query(Schedule).filter(Schedule.form_id == form_id).delete()
        db.flush()
    elif db.query(Schedule).filter(Schedule.form_id == form_id).count() > 0:
        raise ValueError("Schedules already exist for this form. Use replace_existing=True to regenerate.")

    roles = db.query(Role).order_by(Role.role_id).all()
    role_by_name = {role.role_name: role for role in roles}
    active_members = db.query(Member).filter(Member.is_active == True).all()

    qualifications = db.query(MemberRole).filter(MemberRole.is_current == True).all()
    role_to_members: dict[int, list[Member]] = defaultdict(list)
    member_lookup = {member.member_id: member for member in active_members}
    for qualification in qualifications:
        member = member_lookup.get(qualification.member_id)
        if member:
            role_to_members[qualification.role_id].append(member)

    cleaning_leader_role = role_by_name.get("Cleaning Leader")
    cleaning_leader_qualified_ids = {
        member.member_id for member in role_to_members.get(cleaning_leader_role.role_id, [])
    } if cleaning_leader_role else set()

    availability_rows = db.query(AvailabilityEntry).filter(AvailabilityEntry.form_id == form_id, AvailabilityEntry.is_available == True).all()
    available_by_week: dict[int, set[int]] = defaultdict(set)
    for row in availability_rows:
        available_by_week[row.service_week].add(row.member_id)

    conflicts = db.query(RoleConflict).filter(RoleConflict.is_active == True).all()
    conflict_pairs = {tuple(sorted((conflict.role_id_1, conflict.role_id_2))) for conflict in conflicts}

    total_assignments: dict[int, int] = defaultdict(int)
    week_assignments: dict[int, set[int]] = defaultdict(set)
    role_history: dict[tuple[int, int], int] = defaultdict(int)
    prior_week_role_members: dict[int, set[int]] = defaultdict(set)

    created: list[Schedule] = []
    gaps: list[SchedulingGap] = []

    worship_leader_skip_weeks = _worship_leader_skip_weeks(service_dates)

    for service_date in service_dates:
        week = service_date.service_week
        assigned_roles_by_member: dict[int, set[int]] = defaultdict(set)
        cleaning_leader_gap: Optional[SchedulingGap] = None

        role_candidates: dict[int, list[Member]] = {}
        for role in roles:
            role_candidates[role.role_id] = [
                member
                for member in role_to_members.get(role.role_id, [])
                if member.member_id in available_by_week[week]
            ]

        roles_in_priority = sorted(
            roles,
            key=lambda role: (
                len(role_candidates[role.role_id]) / max(role.people_needed, 1),
                0 if role.same_gender_required else 1,
                role.role_id,
            ),
        )

        for role in roles_in_priority:
            if week in worship_leader_skip_weeks and role.role_name == "Worship Leader":
                continue

            candidates = role_candidates[role.role_id]
            if role.same_gender_required:
                assignments, gap = _assign_same_gender_role(
                    role,
                    candidates,
                    week,
                    form_id,
                    total_assignments,
                    week_assignments,
                    role_history,
                    assigned_roles_by_member,
                    conflict_pairs,
                )
            elif role.role_name == "Bible Study Leader" and role.people_needed == 2:
                blocked_member_ids = prior_week_role_members[role.role_id]
                assignments, gap = _assign_bible_study_role(
                    role,
                    candidates,
                    week,
                    form_id,
                    total_assignments,
                    week_assignments,
                    role_history,
                    assigned_roles_by_member,
                    conflict_pairs,
                    blocked_member_ids=blocked_member_ids,
                )
            elif role.role_name == "Cleaner" and role.people_needed == 4:
                assignments, gap = _assign_cleaner_role(
                    role,
                    candidates,
                    week,
                    form_id,
                    total_assignments,
                    week_assignments,
                    role_history,
                    assigned_roles_by_member,
                    conflict_pairs,
                    cleaning_leader_qualified_ids,
                )
            else:
                blocked_member_ids = (
                    prior_week_role_members[role.role_id]
                    if role.role_name == "Bible Study Leader"
                    else set()
                )
                assignments, gap = _assign_standard_role(
                    role,
                    candidates,
                    week,
                    form_id,
                    total_assignments,
                    week_assignments,
                    role_history,
                    assigned_roles_by_member,
                    conflict_pairs,
                    blocked_member_ids=blocked_member_ids,
                )

            if gap:
                if role.role_name == "Cleaning Leader":
                    cleaning_leader_gap = gap
                else:
                    gaps.append(gap)
                continue

            created.extend(assignments)

        if cleaning_leader_role:
            has_cleaning_leader = any(
                assignment.service_week == week and assignment.role_id == cleaning_leader_role.role_id
                for assignment in created
            )
            if not has_cleaning_leader:
                cleaner_assignments = [
                    assignment for assignment in created
                    if assignment.service_week == week and role_by_name.get("Cleaner") and assignment.role_id == role_by_name["Cleaner"].role_id
                ]
                male_cleaner_assignments = [
                    assignment for assignment in cleaner_assignments
                    if member_lookup.get(assignment.member_id) and member_lookup[assignment.member_id].member_gender == "male"
                ]
                if male_cleaner_assignments:
                    fallback_assignment = min(
                        male_cleaner_assignments,
                        key=lambda assignment: (
                            0 if assignment.member_id in cleaning_leader_qualified_ids else 1,
                            total_assignments[assignment.member_id],
                            member_lookup[assignment.member_id].member_name,
                        ),
                    )
                    created.append(
                        Schedule(
                            form_id=form_id,
                            service_week=week,
                            role_id=cleaning_leader_role.role_id,
                            assignment_slot=1,
                            member_id=fallback_assignment.member_id,
                            notes="Auto-generated cleaning leader fallback from cleaner team",
                        )
                    )
                    total_assignments[fallback_assignment.member_id] += 1
                    week_assignments[fallback_assignment.member_id].add(week)
                    role_history[(fallback_assignment.member_id, cleaning_leader_role.role_id)] += 1
                    assigned_roles_by_member[fallback_assignment.member_id].add(cleaning_leader_role.role_id)
                    cleaning_leader_gap = None

        if cleaning_leader_gap:
            gaps.append(cleaning_leader_gap)

        prior_week_role_members = defaultdict(
            set,
            {
                role_id: {assignment.member_id for assignment in created if assignment.service_week == week and assignment.role_id == role_id}
                for role_id in role_candidates.keys()
            },
        )

    for schedule in created:
        db.add(schedule)

    db.commit()

    for schedule in created:
        db.refresh(schedule)

    return SchedulingResult(created=created, gaps=gaps)
