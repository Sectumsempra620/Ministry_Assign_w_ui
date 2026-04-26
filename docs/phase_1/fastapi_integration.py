"""
Church Service Scheduling System - FastAPI Integration Guide
Example endpoints and database interaction patterns
"""

from fastapi import FastAPI, HTTPException, Query, Path, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import datetime, date, timedelta
from typing import List, Optional

# Database session dependency
def get_db() -> Session:
    """Get database session - use with Depends(get_db) in endpoints"""
    # See main.py for SessionLocal setup
    pass


# =============================================================================
# MEMBER MANAGEMENT ENDPOINTS
# =============================================================================

"""
POST   /api/v1/members           - Create new member
GET    /api/v1/members           - List all active members
GET    /api/v1/members/{id}      - Get member details
PUT    /api/v1/members/{id}      - Update member
DELETE /api/v1/members/{id}      - Deactivate member

GET    /api/v1/members/{id}/roles        - Get member's qualifications
POST   /api/v1/members/{id}/roles        - Add role qualification
DELETE /api/v1/members/{id}/roles/{role} - Remove qualification
"""


# =============================================================================
# MONTHLY FORM ENDPOINTS
# =============================================================================

"""
POST   /api/v1/forms                - Create monthly form
GET    /api/v1/forms                - List all forms (with filter by month)
GET    /api/v1/forms/{id}           - Get form details + status
PUT    /api/v1/forms/{id}           - Update form (change status, deadline)
PUT    /api/v1/forms/{id}/status    - Change form status (workflow)
DELETE /api/v1/forms/{id}           - Delete form (careful - cascades!)

GET    /api/v1/forms/{id}/status-report  - Get submission status
"""

# Example workflow for monthly form
"""
1. Admin creates form for April 2026:
   POST /api/v1/forms
   {
     "form_month": "2026-04-01",
     "service_weeks": 4,
     "submission_deadline": "2026-03-27",
     "notes": "Easter Sunday on April 10 - special planning"
   }

2. System initializes availability rows for all active members:
   INSERT INTO availability_entries (form_id, member_id, service_week, is_available)
   -- One row per member per week

3. Admin opens form for submission:
   PUT /api/v1/forms/1/status
   {"status": "open"}

4. Members submit availability:
   POST /api/v1/forms/1/availability
   {
     "member_id": 5,
     "week_1": true,
     "week_2": false,
     "week_3": true,
     "week_4": true,
     "notes": "Out of town week 2"
   }
   
   This updates 4 rows in availability_entries table

5. Admin closes submissions:
   PUT /api/v1/forms/1/status
   {"status": "closed"}

6. Admin creates schedule:
   POST /api/v1/schedules
   {
     "form_id": 1,
     "service_week": 1,
     "role_id": 1,
     "member_id": 5
   }
   -- System validates:
   --   - Member 5 is qualified for role 1
   --   - Member 5 marked available week 1
   --   - No duplicate assignment (unique constraint)
   --   - NO ROLE CONFLICTS: Member 5 doesn't already have a conflicting role that week
   --     * Strong conflicts: Always blocked (e.g., Worship + AV)
   --     * Weak conflicts: Can be overridden if labor shortage (e.g., Worship + Cleaning)
   --   - Form status is 'closed' (optional validation)

7. Admin publishes schedule:
   PUT /api/v1/forms/1/status
   {"status": "published"}
"""


# =============================================================================
# AVAILABILITY ENDPOINTS
# =============================================================================

"""
GET    /api/v1/forms/{id}/service-dates     - Get calendar dates for each week
GET    /api/v1/forms/{id}/availability      - Get all availability for month
POST   /api/v1/forms/{id}/availability      - Member submits/updates
GET    /api/v1/members/{id}/availability    - Get member's full history
GET    /api/v1/forms/{id}/availability-report - Admin report view
"""

# Example: Getting service dates to display in availability form
"""
When member opens availability form, first fetch service_dates:
GET /api/v1/forms/1/service-dates

Response:
{
  "form_id": 1,
  "form_month": "2026-04-01",
  "service_weeks": 4,
  "weeks": [
    {
      "service_week": 1,
      "friday_date": "2026-04-03",
      "formatted_date": "Friday, April 3, 2026",
      "is_holiday": false,
      "notes": "Regular service"
    },
    {
      "service_week": 2,
      "friday_date": "2026-04-10",
      "formatted_date": "Friday, April 10, 2026",
      "is_holiday": true,
      "notes": "Good Friday - special service"
    },
    {
      "service_week": 3,
      "friday_date": "2026-04-17",
      "formatted_date": "Friday, April 17, 2026",
      "is_holiday": false,
      "notes": null
    },
    {
      "service_week": 4,
      "friday_date": "2026-04-24",
      "formatted_date": "Friday, April 24, 2026",
      "is_holiday": false,
      "notes": null
    }
  ]
}

Then member submits availability with clear calendar context.
"""

# Database operation example: Member submitting availability
"""
def submit_availability(
    form_id: int,
    member_id: int,
    availability_data: dict,  # {"week_1": true, "week_2": false, ...}
    db: Session
):
    # Validate
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form or form.status != 'open':
        raise HTTPException(status_code=400, detail="Form not open for submissions")
    
    member = db.query(Member).filter(Member.member_id == member_id).first()
    if not member or not member.is_active:
        raise HTTPException(status_code=404, detail="Member not found or inactive")
    
    # Update all weeks (1 to service_weeks)
    for week_num in range(1, form.service_weeks + 1):
        week_key = f"week_{week_num}"
        if week_key in availability_data:
            entry = db.query(AvailabilityEntry).filter(
                AvailabilityEntry.form_id == form_id,
                AvailabilityEntry.member_id == member_id,
                AvailabilityEntry.service_week == week_num
            ).first()
            
            if entry:
                entry.is_available = availability_data[week_key]
                entry.submitted_at = datetime.utcnow()
            else:
                # Create if doesn't exist (shouldn't happen if form initialized properly)
                entry = AvailabilityEntry(
                    form_id=form_id,
                    member_id=member_id,
                    service_week=week_num,
                    is_available=availability_data[week_key],
                    submitted_at=datetime.utcnow()
                )
                db.add(entry)
    
    db.commit()
    return {"status": "success", "form_id": form_id, "member_id": member_id}
"""


# =============================================================================
# ROLE CONFLICT MANAGEMENT ENDPOINTS
# =============================================================================

"""
POST   /api/v1/role-conflicts         - Create role conflict rule
GET    /api/v1/role-conflicts         - List all active conflicts
PUT    /api/v1/role-conflicts/{id}    - Update conflict (deactivate)
DELETE /api/v1/role-conflicts/{id}    - Delete conflict rule

GET    /api/v1/schedules/check-conflict - Check if assignment would conflict
GET    /api/v1/forms/{id}/conflicts    - Report all conflicts in schedule
"""

# Example: Check conflicts before assignment
"""
def check_schedule_conflicts(
    form_id: int,
    service_week: int,
    member_id: int,
    proposed_role_id: int,
    check_type: str = 'all',  # 'all', 'strong_only', 'weak_allowed'
    db: Session
) -> dict:
    '''
    Returns whether a proposed assignment would create conflicts
    and details about any conflicting assignments.
    
    check_type options:
    - 'all': Check all conflicts (strong + weak)
    - 'strong_only': Only prevent strong conflicts
    - 'weak_allowed': Allow weak conflicts (for labor shortages)
    '''
    
    # Find existing assignments for this member this week
    existing_assignments = db.query(Schedule).filter(
        Schedule.form_id == form_id,
        Schedule.service_week == service_week,
        Schedule.member_id == member_id
    ).all()
    
    conflicts = []
    for existing in existing_assignments:
        # Check if proposed role conflicts with existing role
        conflict = db.query(RoleConflict).filter(
            RoleConflict.is_active == True,
            or_(
                and_(RoleConflict.role_id_1 == existing.role_id, 
                     RoleConflict.role_id_2 == proposed_role_id),
                and_(RoleConflict.role_id_1 == proposed_role_id, 
                     RoleConflict.role_id_2 == existing.role_id)
            )
        ).first()
        
        if conflict:
            # Apply check_type filter
            if check_type == 'all':
                should_block = True  # Block both strong and weak conflicts
            elif check_type == 'strong_only':
                should_block = (conflict.conflict_type == 'strong')  # Only block strong
            elif check_type == 'weak_allowed':
                should_block = (conflict.conflict_type == 'strong')  # Block strong, allow weak
            else:
                should_block = True  # Default to blocking all
            
            if should_block:
                conflicts.append({
                    "existing_schedule_id": existing.schedule_id,
                    "existing_role": existing.role.role_name,
                    "conflict_type": conflict.conflict_type,
                    "conflict_reason": conflict.conflict_reason
                })
    
    return {
        "would_conflict": len(conflicts) > 0,
        "conflicting_assignments": conflicts,
        "check_type_used": check_type,
        "proposed_assignment": {
            "member_id": member_id,
            "role_id": proposed_role_id,
            "service_week": service_week
        }
    }
"""


# =============================================================================
# SCHEDULE ENDPOINTS
# =============================================================================

"""
GET    /api/v1/schedules              - Get all schedules (filtered by form month)
GET    /api/v1/forms/{id}/schedules   - Get full month schedule
GET    /api/v1/forms/{id}/week/{num}  - Get single week view
POST   /api/v1/schedules              - Create assignment
PUT    /api/v1/schedules/{id}         - Update assignment
DELETE /api/v1/schedules/{id}         - Delete assignment
GET    /api/v1/forms/{id}/gaps        - Report missing assignments
"""

# Database operation example: Create schedule assignment
"""
def create_schedule_assignment(
    form_id: int,
    service_week: int,
    role_id: int,
    member_id: int,
    db: Session
):
    # Validation 1: Verify all IDs exist
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    role = db.query(Role).filter(Role.role_id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    member = db.query(Member).filter(Member.member_id == member_id).first()
    if not member or not member.is_active:
        raise HTTPException(status_code=404, detail="Member not found or inactive")
    
    # Validation 2: Member must be qualified for role
    qualification = db.query(MemberRole).filter(
        MemberRole.member_id == member_id,
        MemberRole.role_id == role_id,
        MemberRole.is_current == True
    ).first()
    if not qualification:
        raise HTTPException(
            status_code=400,
            detail=f"{member.first_name} is not qualified for {role.role_name}"
        )
    
    # Validation 3: Member must be available that week
    availability = db.query(AvailabilityEntry).filter(
        AvailabilityEntry.form_id == form_id,
        AvailabilityEntry.member_id == member_id,
        AvailabilityEntry.service_week == service_week
    ).first()
    if not availability or not availability.is_available:
        raise HTTPException(
            status_code=400,
            detail=f"{member.first_name} marked unavailable for week {service_week}"
        )
    
    # If we get here, validation passed
    # Database will enforce UNIQUE(form_id, service_week, role_id)
    schedule = Schedule(
        form_id=form_id,
        service_week=service_week,
        role_id=role_id,
        member_id=member_id
    )
    db.add(schedule)
    
    try:
        db.commit()
        db.refresh(schedule)
        return schedule
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"This role is already assigned for week {service_week}"
        )
"""


# =============================================================================
# REPORTING ENDPOINTS
# =============================================================================

"""
GET /api/v1/reports/current-form-status    - Response rate, who hasn't submitted
GET /api/v1/reports/availability-gaps      - Which roles lack available people
GET /api/v1/reports/schedule-coverage      - Which assignments filled/unfilled
GET /api/v1/reports/member-workload        - Who's assigned to what
GET /api/v1/reports/data-integrity         - Inconsistencies (should be none)
"""

# Example query: Get availability gap report
"""
def get_availability_gaps(form_id: int, db: Session):
    '''
    For each role, show:
    - How many people available for each week
    - Who is available
    - Who is unavailable
    '''
    
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    
    gaps = []
    for role in db.query(Role).all():
        for week in range(1, form.service_weeks + 1):
            
            # Get qualified members available this week
            available = db.query(Member).join(
                MemberRole
            ).filter(
                MemberRole.role_id == role.role_id,
                MemberRole.is_current == True,
                Member.member_id.in_(
                    db.query(AvailabilityEntry.member_id).filter(
                        AvailabilityEntry.form_id == form_id,
                        AvailabilityEntry.service_week == week,
                        AvailabilityEntry.is_available == True
                    )
                )
            ).all()
            
            # Get already assigned
            assigned = db.query(Schedule).filter(
                Schedule.form_id == form_id,
                Schedule.service_week == week,
                Schedule.role_id == role.role_id
            ).first()
            
            gaps.append({
                "week": week,
                "role_name": role.role_name,
                "is_critical": role.is_critical,
                "available_count": len(available),
                "assigned": assigned is not None,
                "candidates": [{"id": m.member_id, "name": f"{m.first_name} {m.last_name}"} 
                              for m in available]
            })
    
    return gaps
"""


# =============================================================================
# SCHEDULING REQUIREMENT VALIDATION
# =============================================================================

# Example: Validate people_needed requirement
"""
def validate_role_assignment_count(
    form_id: int,
    service_week: int,
    role_id: int,
    db: Session
) -> dict:
    '''
    Check if enough people are assigned to a role.
    Args:
        role_id: The role to check
        form_id, service_week: Context
    Returns:
        - people_assigned: Current count
        - people_needed: Required count
        - is_sufficient: Boolean
        - missing_count: How many more needed
    '''
    role = db.query(Role).filter(Role.role_id == role_id).first()
    if not role:
        return {"error": "Role not found"}
    
    assigned_count = db.query(Schedule).filter(
        Schedule.form_id == form_id,
        Schedule.service_week == service_week,
        Schedule.role_id == role_id
    ).count()
    
    return {
        "role_id": role_id,
        "role_name": role.role_name,
        "people_assigned": assigned_count,
        "people_needed": role.people_needed,
        "is_sufficient": assigned_count >= role.people_needed,
        "missing_count": max(0, role.people_needed - assigned_count)
    }
"""

# Example: Validate same_gender_required
"""
def validate_same_gender_requirement(
    form_id: int,
    service_week: int,
    role_id: int,
    db: Session
) -> dict:
    '''
    For roles with same_gender_required=TRUE (e.g., Worship Leader),
    validate all assigned members are the same gender.
    '''
    role = db.query(Role).filter(Role.role_id == role_id).first()
    if not role or not role.same_gender_required:
        return {"requires_same_gender": False, "is_valid": True}
    
    assigned_members = db.query(Schedule).join(Member).filter(
        Schedule.form_id == form_id,
        Schedule.service_week == service_week,
        Schedule.role_id == role_id
    ).all()
    
    if len(assigned_members) == 0:
        return {
            "requires_same_gender": True,
            "is_valid": True,
            "reason": "No members assigned yet"
        }
    
    # Check all members have the same gender
    genders = set(member.member_gender for member in [s.member for s in assigned_members])
    is_valid = len(genders) == 1
    
    return {
        "requires_same_gender": True,
        "assigned_members": len(assigned_members),
        "genders": list(genders),
        "is_valid": is_valid,
        "error": "All assigned members must be same gender" if not is_valid else None
    }
"""

# Example: Validate bible_study_group assignments
"""
def validate_bible_study_distribution(
    form_id: int,
    service_week: int,
    db: Session
) -> dict:
    '''
    Validate that Bible Study Leader role has 1 leader per group
    (tracked via member.bible_study_group field)
    '''
    bible_study_role = db.query(Role).filter(Role.role_name == 'Bible Study Leader').first()
    if not bible_study_role:
        return {"error": "Bible Study Leader role not found"}
    
    assigned = db.query(Schedule).join(Member).filter(
        Schedule.form_id == form_id,
        Schedule.service_week == service_week,
        Schedule.role_id == bible_study_role.role_id
    ).all()
    
    groups = {}
    for schedule in assigned:
        group = schedule.member.bible_study_group
        if group not in groups:
            groups[group] = []
        groups[group].append(schedule.member.member_name)
    
    return {
        "role_name": "Bible Study Leader",
        "groups_covered": len(groups),
        "group_details": groups,
        "is_complete": len(groups) == 2 and all(len(v) >= 1 for v in groups.values()),
        "missing_groups": [g for g in ['group_a', 'group_b'] if g not in groups]
    }
"""


# =============================================================================
# SYSTEM INITIALIZATION
# =============================================================================

"""
When creating a new monthly form, system should:

1. Create MonthlyForm record
2. Initialize AvailabilityEntry rows for all active members (4-5 weeks)
3. Optionally pre-populate with last month's availability as default

def initialize_monthly_form(form_id: int, db: Session):
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    
    # Get all active members
    members = db.query(Member).filter(Member.is_active == True).all()
    
    # Create availability entries for each member x week
    for member in members:
        for week in range(1, form.service_weeks + 1):
            entry = AvailabilityEntry(
                form_id=form_id,
                member_id=member.member_id,
                service_week=week,
                is_available=None,  # Unknown until submitted
                submitted_at=None
            )
            db.add(entry)
    
    db.commit()
"""


# =============================================================================
# FASTAPI STARTUP/DATABASE SETUP
# =============================================================================

"""
# main.py example

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import os

# Database connection
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://user:password@localhost:3306/church_scheduling"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL logging
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600  # Recycle connections every hour
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables on startup
from models import Base
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Church Scheduling System")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Import and include routers
from routers import members, forms, availability, schedules, reports

app.include_router(members.router, prefix="/api/v1", tags=["members"])
app.include_router(forms.router, prefix="/api/v1", tags=["forms"])
app.include_router(availability.router, prefix="/api/v1", tags=["availability"])
app.include_router(schedules.router, prefix="/api/v1", tags=["schedules"])
app.include_router(reports.router, prefix="/api/v1", tags=["reports"])

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""


# =============================================================================
# ENVIRONMENT & TESTING
# =============================================================================

"""
# .env file for local development
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/church_scheduling
DEBUG=true
LOG_LEVEL=INFO

# For AWS RDS:
DATABASE_URL=mysql+pymysql://admin:password@church-db.xxxxx.us-east-1.rds.amazonaws.com:3306/church_scheduling

# pytest test example
def test_create_schedule_assignment(client, db):
    # Setup
    form = MonthlyForm(form_month="2026-04-01", service_weeks=4, status="closed")
    db.add(form)
    db.commit()
    
    member = Member(first_name="John", last_name="Smith", is_active=True)
    db.add(member)
    db.commit()
    
    role = Role(role_name="Worship Leader", is_critical=True)
    db.add(role)
    db.commit()
    
    qualification = MemberRole(member_id=member.member_id, role_id=role.role_id)
    db.add(qualification)
    db.commit()
    
    availability = AvailabilityEntry(
        form_id=form.form_id,
        member_id=member.member_id,
        service_week=1,
        is_available=True
    )
    db.add(availability)
    db.commit()
    
    # Test
    response = client.post("/api/v1/schedules", json={
        "form_id": form.form_id,
        "service_week": 1,
        "role_id": role.role_id,
        "member_id": member.member_id
    })
    
    assert response.status_code == 201
    assert response.json()["role_id"] == role.role_id
"""

print(__doc__)
