"""
Church Service Scheduling System - FastAPI Backend
Main application with all endpoints for member, form, and scheduling management
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, selectinload
from sqlalchemy.pool import NullPool
from datetime import datetime, date, timedelta
from typing import List, Optional
import os
from dotenv import load_dotenv

from backend.scheduler import generate_schedule
from backend.rescheduler import list_replacement_candidates, process_open_reschedule_requests

# Import all models
from models import (
    Base, Member, Role, MemberRole, MonthlyForm, ServiceDate,
    AvailabilityEntry, Schedule, RescheduleRequest, RescheduleRequestCandidate, RoleConflict,
    # Pydantic models
    MemberCreate, MemberUpdate, MemberResponse, MemberWithRoles,
    RoleResponse,
    MemberRoleCreate, MemberRoleResponse,
    MonthlyFormCreate, MonthlyFormUpdate, MonthlyFormResponse,
    ServiceDateCreate, ServiceDateResponse,
    AvailabilityEntryCreate, AvailabilityEntryResponse,
    ScheduleCreate, ScheduleResponse,
    RescheduleRequestCreate, RescheduleRequestResponse, ReplacementCandidateResponse,
)

PERIOD_START_MONTHS = {3, 6, 9, 12}


def normalize_period_start(period_start: date) -> date:
    normalized = period_start.replace(day=1)
    if normalized.month not in PERIOD_START_MONTHS:
        raise HTTPException(
            status_code=400,
            detail="Service period must start in March, June, September, or December.",
        )
    return normalized


def get_period_end(period_start: date) -> date:
    if period_start.month == 12:
        return date(period_start.year + 1, 2, 1)
    return date(period_start.year, period_start.month + 2, 1)


def get_period_last_day(period_start: date) -> date:
    if period_start.month == 12:
        return date(period_start.year + 1, 3, 1) - timedelta(days=1)
    return date(period_start.year, period_start.month + 3, 1) - timedelta(days=1)


def get_period_fridays(period_start: date) -> List[date]:
    current = period_start
    fridays: List[date] = []
    period_last_day = get_period_last_day(period_start)

    while current <= period_last_day:
        if current.weekday() == 4:
            fridays.append(current)
        current += timedelta(days=1)

    return fridays


def count_fridays_in_period(period_start: date) -> int:
    return len(get_period_fridays(period_start))


def format_period_label(period_start: date) -> str:
    period_end = get_period_end(period_start)
    if period_start.year == period_end.year:
        return f"{period_start.strftime('%b')}–{period_end.strftime('%b %Y')}"
    return f"{period_start.strftime('%b %Y')}–{period_end.strftime('%b %Y')}"

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://admin:password@your-rds-endpoint:3306/church_tech_ministry"
)

engine_kwargs = {
    "echo": True,  # Set to False in production
    "pool_pre_ping": True,
    "pool_recycle": 3600,
    "poolclass": NullPool,
}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

# Create database engine and session
engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables
Base.metadata.create_all(bind=engine)


def load_members_with_roles(is_active: Optional[bool] = None, member_id: Optional[int] = None):
    """Read members and role qualifications using a fresh connection."""
    read_engine = create_engine(DATABASE_URL, pool_pre_ping=True, poolclass=NullPool)
    filters = []
    params = {}

    if is_active is not None:
        filters.append("m.is_active = :is_active")
        params["is_active"] = is_active

    if member_id is not None:
        filters.append("m.member_id = :member_id")
        params["member_id"] = member_id

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""

    query = text(f"""
        SELECT
            m.member_id,
            m.member_name,
            m.member_gender,
            m.email,
            m.is_active,
            m.bible_study_group,
            m.is_senior_for_pairing,
            mr.member_role_id,
            mr.role_id,
            mr.is_current,
            mr.qualified_date,
            r.role_name
        FROM members m
        LEFT JOIN member_roles mr ON mr.member_id = m.member_id AND mr.is_current = TRUE
        LEFT JOIN roles r ON r.role_id = mr.role_id
        {where_clause}
        ORDER BY m.member_id, mr.member_role_id
    """)

    with read_engine.connect() as conn:
        rows = conn.execute(query, params).mappings().all()

    members = {}
    for row in rows:
        if row["member_id"] not in members:
            members[row["member_id"]] = {
                "member_id": row["member_id"],
                "member_name": row["member_name"],
                "member_gender": row["member_gender"],
                "email": row["email"],
                "is_active": bool(row["is_active"]),
                "bible_study_group": row["bible_study_group"],
                "is_senior_for_pairing": bool(row["is_senior_for_pairing"]),
                "roles": []
            }

        if row["member_role_id"] is not None:
            members[row["member_id"]]["roles"].append({
                "member_role_id": row["member_role_id"],
                "member_id": row["member_id"],
                "role_id": row["role_id"],
                "role_name": row["role_name"],
                "is_current": bool(row["is_current"]),
                "qualified_date": row["qualified_date"]
            })

    return list(members.values())


def serialize_reschedule_request(request: RescheduleRequest) -> dict:
    return {
        "request_id": request.request_id,
        "schedule_id": request.schedule_id,
        "form_id": request.form_id,
        "service_week": request.service_week,
        "role_id": request.role_id,
        "role_name": request.role.role_name if request.role else "",
        "requesting_member_id": request.requesting_member_id,
        "original_member_id": request.original_member_id,
        "original_member_name": request.original_member.member_name if request.original_member else "",
        "reason": request.reason,
        "status": request.status,
        "submitted_at": request.submitted_at,
        "processed_at": request.processed_at,
        "processed_note": request.processed_note,
        "preferred_candidates": [
            {
                "member_id": candidate.member_id,
                "member_name": candidate.member.member_name if candidate.member else "",
            }
            for candidate in request.candidates
        ],
    }


def get_db():
    """Dependency: Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="Church Service Scheduling API",
    description="API for managing service scheduling, member availability, and role assignments",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
def health_check():
    """Check if API and database are operational"""
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }, 500


@app.get("/debug/db-members")
def debug_db_members():
    """Temporary debug endpoint for comparing live server DB reads."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT member_id, member_name, is_active
            FROM members
            ORDER BY member_id
        """)).mappings().all()

    return {
        "database_url": DATABASE_URL.rsplit("@", 1)[-1],
        "row_count": len(rows),
        "rows": [
            {
                "member_id": row["member_id"],
                "member_name": row["member_name"],
                "is_active": bool(row["is_active"]),
            }
            for row in rows
        ]
    }


# ============================================================================
# MEMBER ENDPOINTS
# ============================================================================

@app.post("/api/v1/members", response_model=MemberResponse, status_code=201)
def create_member(member: MemberCreate, db: Session = Depends(get_db)):
    """Create a new member"""
    qualified_roles = member.qualified_roles or []

    # Check if email already exists
    if member.email:
        existing = db.query(Member).filter(Member.email == member.email).first()
        if existing:
            if existing.is_active:
                raise HTTPException(
                    status_code=400,
                    detail=f"Email {member.email} already registered"
                )

            existing.member_name = member.member_name
            existing.member_gender = member.member_gender
            existing.phone = member.phone
            existing.joined_date = member.joined_date or existing.joined_date or date.today()
            existing.bible_study_group = member.bible_study_group
            existing.is_senior_for_pairing = member.is_senior_for_pairing
            existing.is_active = True

            for role_id in qualified_roles:
                role = db.query(Role).filter(Role.role_id == role_id).first()
                if not role:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Role with ID {role_id} does not exist"
                    )

                existing_qual = db.query(MemberRole).filter(
                    MemberRole.member_id == existing.member_id,
                    MemberRole.role_id == role_id
                ).first()

                if existing_qual:
                    existing_qual.is_current = True
                    if not existing_qual.qualified_date:
                        existing_qual.qualified_date = date.today()
                else:
                    db.add(MemberRole(
                        member_id=existing.member_id,
                        role_id=role_id,
                        qualified_date=date.today()
                    ))

            db.commit()
            db.refresh(existing)
            return existing
    
    db_member = Member(
        member_name=member.member_name,
        member_gender=member.member_gender,
        email=member.email,
        phone=member.phone,
        joined_date=member.joined_date or date.today(),
        bible_study_group=member.bible_study_group,
        is_senior_for_pairing=member.is_senior_for_pairing
    )
    db.add(db_member)
    db.commit()
    db.refresh(db_member)
    
    # Add role qualifications if provided
    if qualified_roles:
        for role_id in qualified_roles:
            # Verify role exists
            role = db.query(Role).filter(Role.role_id == role_id).first()
            if not role:
                raise HTTPException(
                    status_code=400,
                    detail=f"Role with ID {role_id} does not exist"
                )
            
            # Check if qualification already exists
            existing_qual = db.query(MemberRole).filter(
                MemberRole.member_id == db_member.member_id,
                MemberRole.role_id == role_id
            ).first()
            
            if not existing_qual:
                db_qual = MemberRole(
                    member_id=db_member.member_id,
                    role_id=role_id,
                    qualified_date=date.today()
                )
                db.add(db_qual)
        
        db.commit()
    
    return db_member


@app.get("/api/v1/members", response_model=List[MemberWithRoles])
def list_members(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """List all members with their qualified roles"""
    return load_members_with_roles(is_active=is_active)


@app.get("/api/v1/members/{member_id}", response_model=MemberWithRoles)
def get_member(member_id: int, db: Session = Depends(get_db)):
    """Get a specific member with all their roles"""
    members = load_members_with_roles(member_id=member_id)
    if not members:
        raise HTTPException(status_code=404, detail="Member not found")
    return members[0]


@app.put("/api/v1/members/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: int,
    member_update: MemberUpdate,
    db: Session = Depends(get_db)
):
    """Update member details"""
    member = db.query(Member).filter(Member.member_id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    update_data = member_update.model_dump(exclude_unset=True)
    qualified_roles = update_data.pop("qualified_roles", None)

    for field, value in update_data.items():
        setattr(member, field, value)

    if qualified_roles is not None:
        requested_role_ids = set(qualified_roles)
        existing_roles = db.query(MemberRole).filter(MemberRole.member_id == member_id).all()
        existing_by_role_id = {member_role.role_id: member_role for member_role in existing_roles}

        for role_id in requested_role_ids:
            role = db.query(Role).filter(Role.role_id == role_id).first()
            if not role:
                raise HTTPException(
                    status_code=400,
                    detail=f"Role with ID {role_id} does not exist"
                )

            existing_role = existing_by_role_id.get(role_id)
            if existing_role:
                existing_role.is_current = True
                if not existing_role.qualified_date:
                    existing_role.qualified_date = date.today()
            else:
                db.add(
                    MemberRole(
                        member_id=member_id,
                        role_id=role_id,
                        qualified_date=date.today(),
                        is_current=True,
                    )
                )

        for role_id, existing_role in existing_by_role_id.items():
            if role_id not in requested_role_ids:
                existing_role.is_current = False
    
    db.commit()
    db.refresh(member)
    return member


@app.delete("/api/v1/members/{member_id}", status_code=204)
def delete_member(member_id: int, db: Session = Depends(get_db)):
    """Delete (deactivate) a member"""
    member = db.query(Member).filter(Member.member_id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    member.is_active = False
    db.commit()


# ============================================================================
# ROLE ENDPOINTS
# ============================================================================

@app.get("/api/v1/roles", response_model=List[RoleResponse])
def list_roles(db: Session = Depends(get_db)):
    """List all available roles"""
    return db.query(Role).all()


@app.post("/api/v1/member-roles", response_model=MemberRoleResponse, status_code=201)
def add_member_role(
    member_role: MemberRoleCreate,
    db: Session = Depends(get_db)
):
    """Add a role qualification to a member"""
    # Verify member exists
    member = db.query(Member).filter(Member.member_id == member_role.member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Verify role exists
    role = db.query(Role).filter(Role.role_id == member_role.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Check if already qualified
    existing = db.query(MemberRole).filter(
        MemberRole.member_id == member_role.member_id,
        MemberRole.role_id == member_role.role_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Member already qualified for {role.role_name}"
        )
    
    db_member_role = MemberRole(
        member_id=member_role.member_id,
        role_id=member_role.role_id,
        notes=member_role.notes
    )
    db.add(db_member_role)
    db.commit()
    db.refresh(db_member_role)
    return db_member_role


# ============================================================================
# MONTHLY FORM ENDPOINTS
# ============================================================================

@app.post("/api/v1/forms", response_model=MonthlyFormResponse, status_code=201)
def create_monthly_form(form: MonthlyFormCreate, db: Session = Depends(get_db)):
    """Create a new three-month service period form"""
    period_start = normalize_period_start(form.form_month)
    service_weeks = count_fridays_in_period(period_start)

    # Check if form already exists for this service period
    existing = db.query(MonthlyForm).filter(
        MonthlyForm.form_month == period_start,
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Service period form for {format_period_label(period_start)} already exists"
        )
    
    db_form = MonthlyForm(
        form_month=period_start,
        service_weeks=service_weeks,
        submission_deadline=form.submission_deadline,
        notes=form.notes,
        status='draft'
    )
    db.add(db_form)
    db.commit()
    db.refresh(db_form)
    return db_form


@app.get("/api/v1/forms", response_model=List[MonthlyFormResponse])
def list_forms(db: Session = Depends(get_db)):
    """List all service period forms"""
    return db.query(MonthlyForm).order_by(MonthlyForm.form_month.desc()).all()


@app.get("/api/v1/forms/{form_id}", response_model=MonthlyFormResponse)
def get_form(form_id: int, db: Session = Depends(get_db)):
    """Get a specific form"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


@app.put("/api/v1/forms/{form_id}/status", response_model=MonthlyFormResponse)
def update_form_status(
    form_id: int,
    status_update: dict,
    db: Session = Depends(get_db)
):
    """Change form status (draft → open → closed → published)"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    new_status = status_update.get("status")
    if new_status not in ['draft', 'open', 'closed', 'published']:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    form.status = new_status
    db.commit()
    db.refresh(form)
    return form


# ============================================================================
# SERVICE DATES ENDPOINTS
# ============================================================================

@app.get("/api/v1/forms/{form_id}/service-dates", response_model=List[ServiceDateResponse])
def get_service_dates(form_id: int, db: Session = Depends(get_db)):
    """Get all service dates for a form"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    return db.query(ServiceDate).filter(
        ServiceDate.form_id == form_id
    ).order_by(ServiceDate.service_week).all()


@app.post("/api/v1/service-dates", response_model=ServiceDateResponse, status_code=201)
def create_service_date(service_date: ServiceDateCreate, db: Session = Depends(get_db)):
    """Create a service date mapping"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == service_date.form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    db_service_date = ServiceDate(
        form_id=service_date.form_id,
        service_week=service_date.service_week,
        friday_date=service_date.friday_date,
        is_holiday=service_date.is_holiday,
        notes=service_date.notes
    )
    db.add(db_service_date)
    db.commit()
    db.refresh(db_service_date)
    return db_service_date


@app.post("/api/v1/forms/{form_id}/generate-service-dates", response_model=List[ServiceDateResponse], status_code=201)
def generate_service_dates(form_id: int, replace_existing: bool = True, db: Session = Depends(get_db)):
    """Generate every Friday in the form's three-month service period."""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    period_start = normalize_period_start(form.form_month)
    fridays = get_period_fridays(period_start)

    existing_dates = db.query(ServiceDate).filter(ServiceDate.form_id == form_id).all()
    if existing_dates and not replace_existing:
        raise HTTPException(
            status_code=400,
            detail="This service period already has Friday dates configured.",
        )

    if existing_dates:
        db.query(ServiceDate).filter(ServiceDate.form_id == form_id).delete()
        db.flush()

    created_dates = []
    for index, friday in enumerate(fridays, start=1):
        service_date = ServiceDate(
            form_id=form_id,
            service_week=index,
            friday_date=friday,
        )
        db.add(service_date)
        created_dates.append(service_date)

    form.service_weeks = len(fridays)
    db.commit()

    for service_date in created_dates:
        db.refresh(service_date)

    return created_dates


# ============================================================================
# AVAILABILITY ENDPOINTS
# ============================================================================

@app.post("/api/v1/availability", response_model=List[AvailabilityEntryResponse], status_code=201)
def submit_availability(
    form_id: int,
    member_id: int,
    availability_data: dict,  # {"week_1": true, "week_2": false, ...}
    db: Session = Depends(get_db)
):
    """Submit member availability for a service period"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    if form.status != 'open':
        raise HTTPException(status_code=400, detail="Form is not open for submissions")
    
    member = db.query(Member).filter(Member.member_id == member_id).first()
    if not member or not member.is_active:
        raise HTTPException(status_code=404, detail="Member not found or inactive")
    
    entries = []
    for week_num in range(1, form.service_weeks + 1):
        week_key = f"week_{week_num}"
        if week_key in availability_data:
            week_reason_key = f"week_reason_{week_num}"
            week_reason = availability_data.get(week_reason_key) or None
            # Get or create entry
            entry = db.query(AvailabilityEntry).filter(
                AvailabilityEntry.form_id == form_id,
                AvailabilityEntry.member_id == member_id,
                AvailabilityEntry.service_week == week_num
            ).first()
            
            if not entry:
                entry = AvailabilityEntry(
                    form_id=form_id,
                    member_id=member_id,
                    service_week=week_num,
                    is_available=availability_data[week_key],
                    notes=week_reason,
                    submitted_at=datetime.utcnow()
                )
                db.add(entry)
            else:
                entry.is_available = availability_data[week_key]
                entry.notes = week_reason
                entry.submitted_at = datetime.utcnow()
            
            entries.append(entry)
    
    db.commit()
    for entry in entries:
        db.refresh(entry)
    return entries


@app.get("/api/v1/forms/{form_id}/availability", response_model=List[AvailabilityEntryResponse])
def get_form_availability(form_id: int, db: Session = Depends(get_db)):
    """Get all availability entries for a form"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    return db.query(AvailabilityEntry).filter(
        AvailabilityEntry.form_id == form_id
    ).order_by(AvailabilityEntry.member_id, AvailabilityEntry.service_week).all()


# ============================================================================
# SCHEDULE ENDPOINTS
# ============================================================================

@app.post("/api/v1/schedules", response_model=ScheduleResponse, status_code=201)
def create_schedule(schedule: ScheduleCreate, db: Session = Depends(get_db)):
    """Create a schedule assignment"""
    # Verify all foreign keys
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == schedule.form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    role = db.query(Role).filter(Role.role_id == schedule.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    member = db.query(Member).filter(Member.member_id == schedule.member_id).first()
    if not member or not member.is_active:
        raise HTTPException(status_code=404, detail="Member not found or inactive")
    
    # Check qualifications
    qualified = db.query(MemberRole).filter(
        MemberRole.member_id == schedule.member_id,
        MemberRole.role_id == schedule.role_id,
        MemberRole.is_current == True
    ).first()
    
    if not qualified:
        raise HTTPException(
            status_code=400,
            detail=f"Member is not qualified for {role.role_name}"
        )
    
    # Check availability
    available = db.query(AvailabilityEntry).filter(
        AvailabilityEntry.form_id == schedule.form_id,
        AvailabilityEntry.member_id == schedule.member_id,
        AvailabilityEntry.service_week == schedule.service_week,
        AvailabilityEntry.is_available == True
    ).first()
    
    if not available:
        raise HTTPException(
            status_code=400,
            detail=f"Member is not available for week {schedule.service_week}"
        )

    assignment_slot = schedule.assignment_slot
    if assignment_slot is None:
        current_max_slot = db.query(Schedule).filter(
            Schedule.form_id == schedule.form_id,
            Schedule.service_week == schedule.service_week,
            Schedule.role_id == schedule.role_id,
        ).count()
        assignment_slot = current_max_slot + 1
    
    db_schedule = Schedule(
        form_id=schedule.form_id,
        service_week=schedule.service_week,
        role_id=schedule.role_id,
        assignment_slot=assignment_slot,
        member_id=schedule.member_id,
        notes=schedule.notes,
    )
    
    try:
        db.add(db_schedule)
        db.commit()
        db.refresh(db_schedule)
        return db_schedule
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Schedule conflict: {str(e)}")


@app.get("/api/v1/schedules", response_model=List[ScheduleResponse])
def list_schedules(form_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List schedules (optionally filtered by form)"""
    query = db.query(Schedule)
    if form_id:
        query = query.filter(Schedule.form_id == form_id)
    return query.order_by(Schedule.form_id, Schedule.service_week, Schedule.role_id, Schedule.assignment_slot).all()


@app.get("/api/v1/forms/{form_id}/schedules", response_model=List[ScheduleResponse])
def get_form_schedules(form_id: int, db: Session = Depends(get_db)):
    """Get all schedules for a form"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    return db.query(Schedule).filter(Schedule.form_id == form_id).order_by(
        Schedule.service_week, Schedule.role_id, Schedule.assignment_slot
    ).all()


@app.get("/api/v1/schedules/{schedule_id}/replacement-candidates", response_model=List[ReplacementCandidateResponse])
def get_replacement_candidates(schedule_id: int, db: Session = Depends(get_db)):
    """List possible replacement candidates for one assignment."""
    schedule = db.query(Schedule).filter(Schedule.schedule_id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return list_replacement_candidates(db, schedule)


@app.post("/api/v1/reschedule-requests", response_model=RescheduleRequestResponse, status_code=201)
def create_reschedule_request(request_data: RescheduleRequestCreate, db: Session = Depends(get_db)):
    """Submit a request to replace one existing assignment."""
    reason = request_data.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required for rescheduling.")

    schedule = (
        db.query(Schedule)
        .filter(Schedule.schedule_id == request_data.schedule_id)
        .first()
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule.member_id != request_data.requesting_member_id:
        raise HTTPException(
            status_code=400,
            detail="Members can only submit a reschedule request for their own assignment.",
        )

    service_date = (
        db.query(ServiceDate)
        .filter(
            ServiceDate.form_id == schedule.form_id,
            ServiceDate.service_week == schedule.service_week,
        )
        .first()
    )
    if not service_date:
        raise HTTPException(status_code=400, detail="Service date is not configured for this assignment.")

    if service_date.friday_date <= date.today():
        raise HTTPException(
            status_code=400,
            detail="Replacement requests can only be submitted for service dates after today.",
        )

    existing_open_request = (
        db.query(RescheduleRequest)
        .filter(
            RescheduleRequest.schedule_id == schedule.schedule_id,
            RescheduleRequest.status == "open",
        )
        .first()
    )
    if existing_open_request:
        raise HTTPException(status_code=400, detail="An open reschedule request already exists for this assignment.")

    preferred_candidate_ids = request_data.preferred_candidate_ids or []
    valid_candidate_ids = {item["member_id"] for item in list_replacement_candidates(db, schedule)}
    invalid_candidate_ids = [candidate_id for candidate_id in preferred_candidate_ids if candidate_id not in valid_candidate_ids]
    if invalid_candidate_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Some preferred candidates are not valid replacements: {invalid_candidate_ids}",
        )

    request = RescheduleRequest(
        schedule_id=schedule.schedule_id,
        form_id=schedule.form_id,
        service_week=schedule.service_week,
        role_id=schedule.role_id,
        requesting_member_id=request_data.requesting_member_id,
        original_member_id=schedule.member_id,
        reason=reason,
    )
    db.add(request)
    db.flush()

    for candidate_id in preferred_candidate_ids:
        db.add(
            RescheduleRequestCandidate(
                request_id=request.request_id,
                member_id=candidate_id,
            )
        )

    db.commit()
    db.refresh(request)
    return serialize_reschedule_request(request)


@app.get("/api/v1/forms/{form_id}/reschedule-requests", response_model=List[RescheduleRequestResponse])
def list_form_reschedule_requests(form_id: int, status: Optional[str] = None, db: Session = Depends(get_db)):
    """List reschedule requests for a form."""
    query = db.query(RescheduleRequest).filter(RescheduleRequest.form_id == form_id)
    if status:
        query = query.filter(RescheduleRequest.status == status)

    requests = query.order_by(
        RescheduleRequest.service_week,
        RescheduleRequest.submitted_at.desc(),
        RescheduleRequest.request_id.desc(),
    ).all()
    return [serialize_reschedule_request(request) for request in requests]


@app.post("/api/v1/forms/{form_id}/reschedule")
def apply_reschedule_requests(form_id: int, db: Session = Depends(get_db)):
    """Apply all open reschedule requests for one form."""
    result = process_open_reschedule_requests(db=db, form_id=form_id)
    return {
        "form_id": form_id,
        "applied_weeks": [
            {
                "week": week_result.week,
                "request_ids": week_result.request_ids,
                "changed_schedule_ids": week_result.changed_schedule_ids,
                "note": week_result.note,
            }
            for week_result in result.applied_weeks
        ],
        "unresolved_weeks": [
            {
                "week": week_result.week,
                "request_ids": week_result.request_ids,
                "changed_schedule_ids": week_result.changed_schedule_ids,
                "note": week_result.note,
            }
            for week_result in result.unresolved_weeks
        ],
    }


@app.post("/api/v1/forms/{form_id}/auto-schedule")
def auto_schedule_form(form_id: int, replace_existing: bool = False, db: Session = Depends(get_db)):
    """Automatically generate a schedule for a form using qualifications and availability."""
    try:
        result = generate_schedule(form_id=form_id, db=db, replace_existing=replace_existing)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "form_id": form_id,
        "created_count": len(result.created),
        "gaps": [
            {
                "week": gap.week,
                "role_id": gap.role_id,
                "role_name": gap.role_name,
                "required_slots": gap.required_slots,
                "filled_slots": gap.filled_slots,
                "reason": gap.reason,
            }
            for gap in result.gaps
        ],
    }


# ============================================================================
# REPORTING ENDPOINTS
# ============================================================================

@app.get("/api/v1/forms/{form_id}/report")
def get_form_report(form_id: int, db: Session = Depends(get_db)):
    """Get a comprehensive report for a service period form"""
    form = db.query(MonthlyForm).filter(MonthlyForm.form_id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    
    members = db.query(Member).filter(Member.is_active == True).all()
    total_members = len(members)
    
    # Submission status
    submissions = db.query(AvailabilityEntry).filter(
        AvailabilityEntry.form_id == form_id,
        AvailabilityEntry.submitted_at.isnot(None)
    ).distinct(AvailabilityEntry.member_id).count()
    
    # Scheduled count
    scheduled = db.query(Schedule).filter(Schedule.form_id == form_id).count()
    
    # Service dates count
    service_dates = db.query(ServiceDate).filter(ServiceDate.form_id == form_id).count()
    
    return {
        "form_id": form_id,
        "form_month": format_period_label(form.form_month),
        "status": form.status,
        "total_members": total_members,
        "submissions": submissions,
        "submission_rate": f"{(submissions/total_members*100):.1f}%" if total_members > 0 else "0%",
        "service_weeks": form.service_weeks,
        "service_dates_configured": service_dates,
        "assignments_created": scheduled
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint"""
    try:
        # Test database connection by counting members
        count = db.query(Member).count()
        return {"status": "healthy", "database": "connected", "members_count": count}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
def root():
    """API root endpoint"""
    return {
        "message": "Church Service Scheduling API",
        "documentation": "/docs",
        "health": "/health",
        "version": "1.0.0"
    }


# ============================================================================
# RUN APP
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
