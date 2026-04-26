"""
Church Service Scheduling System - FastAPI Models
SQLAlchemy ORM models matching the MySQL schema
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Enum, ForeignKey, UniqueConstraint, Index, Text, ForeignKeyConstraint, CheckConstraint
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, date
from pydantic import BaseModel, EmailStr
from typing import Optional, List

# SQLAlchemy ORM Models
Base = declarative_base()


class Member(Base):
    """
    Represents a church member who can be assigned to service roles.
    One member can have multiple role qualifications.
    """
    __tablename__ = "members"
    
    member_id = Column(Integer, primary_key=True)
    member_name = Column(String(100), nullable=False)
    member_gender = Column(Enum('male', 'female'), nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    joined_date = Column(Date, nullable=True)
    bible_study_group = Column(Enum('group_a', 'group_b'), nullable=True)
    is_senior_for_pairing = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    member_roles = relationship("MemberRole", back_populates="member", cascade="all, delete-orphan")
    availability_entries = relationship("AvailabilityEntry", back_populates="member", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="member", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_members_full_name', 'member_name'),
        Index('idx_members_email', 'email'),
        Index('idx_members_is_active', 'is_active'),
        Index('idx_members_bible_study_group', 'bible_study_group'),
    )

    @property
    def roles(self):
        """Compatibility property for API responses that expect `roles`."""
        return self.member_roles


class Role(Base):
    """
    Represents a service role (Worship Leader, AV, Cleaning, etc.)
    Includes scheduling requirements like people_needed and gender_matching.
    Extensible - add new roles without schema changes.
    """
    __tablename__ = "roles"
    
    role_id = Column(Integer, primary_key=True)
    role_name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    people_needed = Column(Integer, default=1)  # How many people needed per service
    same_gender_required = Column(Boolean, default=False)  # All assigned must be same gender
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    member_roles = relationship("MemberRole", back_populates="role", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="role", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_roles_role_name', 'role_name'),
    )


class MemberRole(Base):
    """
    Junction table: Records which members are qualified for which roles.
    Supports many-to-many relationship and qualification history.
    """
    __tablename__ = "member_roles"
    
    member_role_id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey("members.member_id", ondelete="CASCADE"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False)
    qualified_date = Column(Date, default=date.today)
    is_current = Column(Boolean, default=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    member = relationship("Member", back_populates="member_roles")
    role = relationship("Role", back_populates="member_roles")
    
    __table_args__ = (
        UniqueConstraint('member_id', 'role_id', name='unique_member_role'),
        Index('idx_member_roles_member_id', 'member_id'),
        Index('idx_member_roles_role_id', 'role_id'),
        Index('idx_member_roles_is_current', 'is_current'),
    )

    @property
    def role_name(self):
        """Expose the related role name for API serialization."""
        return self.role.role_name if self.role else None


class MonthlyForm(Base):
    """
    Represents a three-month availability submission cycle.
    One form per service period (enforced by unique constraint).
    Workflow: draft → open → closed → published
    """
    __tablename__ = "monthly_forms"
    
    form_id = Column(Integer, primary_key=True)
    form_month = Column(Date, nullable=False, unique=True)  # First day of the service period (Mar/Jun/Sep/Dec)
    service_weeks = Column(Integer, default=13)  # Total Fridays in the three-month period
    submission_deadline = Column(Date, nullable=True)
    status = Column(
        Enum('draft', 'open', 'closed', 'published', name='form_status'),
        default='draft'
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    service_dates = relationship("ServiceDate", back_populates="form", cascade="all, delete-orphan")
    availability_entries = relationship("AvailabilityEntry", back_populates="form", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="form", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_monthly_forms_form_month', 'form_month'),
        Index('idx_monthly_forms_status', 'status'),
    )


class ServiceDate(Base):
    """
    Maps each service week to an actual Friday date.
    Helps members understand which calendar date each week refers to.
    One entry per week per monthly form.
    """
    __tablename__ = "service_dates"
    
    service_date_id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey("monthly_forms.form_id", ondelete="CASCADE"), nullable=False)
    service_week = Column(Integer, nullable=False)  # 1-5
    friday_date = Column(Date, nullable=False)
    is_holiday = Column(Boolean, default=False)  # TRUE for holidays (Easter, Thanksgiving, etc.)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    form = relationship("MonthlyForm", back_populates="service_dates")
    
    __table_args__ = (
        UniqueConstraint('form_id', 'service_week', name='unique_week_date'),
        UniqueConstraint('form_id', 'friday_date', name='unique_friday_per_form'),
        Index('idx_service_dates_form_id', 'form_id'),
        Index('idx_service_dates_friday_date', 'friday_date'),
        Index('idx_service_dates_is_holiday', 'is_holiday'),
    )


class AvailabilityEntry(Base):
    """
    Records member availability responses for each Friday in the month.
    One entry per member per week per form.
    Members indicate availability at week level (role assignment happens later).
    """
    __tablename__ = "availability_entries"
    
    availability_id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey("monthly_forms.form_id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.member_id", ondelete="CASCADE"), nullable=False)
    service_week = Column(Integer, nullable=False)  # 1-5
    is_available = Column(Boolean, nullable=False)
    notes = Column(String(500), nullable=True)
    submitted_at = Column(DateTime, nullable=True)  # NULL = not yet submitted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    form = relationship("MonthlyForm", back_populates="availability_entries")
    member = relationship("Member", back_populates="availability_entries")
    
    __table_args__ = (
        UniqueConstraint('form_id', 'member_id', 'service_week', name='unique_member_form_week'),
        Index('idx_availability_entries_form_id', 'form_id'),
        Index('idx_availability_entries_member_id', 'member_id'),
        Index('idx_availability_entries_is_available', 'is_available'),
        Index('idx_availability_entries_submitted_at', 'submitted_at'),
    )


class Schedule(Base):
    """
    Final service schedule assignments.
    Records when a member is assigned to a role for a specific week.
    Constraint: Only one member per role per week (enforced by unique constraint).
    """
    __tablename__ = "schedules"
    
    schedule_id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey("monthly_forms.form_id", ondelete="CASCADE"), nullable=False)
    service_week = Column(Integer, nullable=False)  # 1-5
    role_id = Column(Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False)
    assignment_slot = Column(Integer, nullable=False, default=1)
    member_id = Column(Integer, ForeignKey("members.member_id", ondelete="CASCADE"), nullable=False)
    notes = Column(String(500), nullable=True)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    form = relationship("MonthlyForm", back_populates="schedules")
    role = relationship("Role", back_populates="schedules")
    member = relationship("Member", back_populates="schedules")
    
    __table_args__ = (
        UniqueConstraint('form_id', 'service_week', 'role_id', 'assignment_slot', name='unique_week_role_assignment_slot'),
        Index('idx_schedules_form_id', 'form_id'),
        Index('idx_schedules_member_id', 'member_id'),
        Index('idx_schedules_role_id', 'role_id'),
        Index('idx_schedules_week', 'service_week'),
        Index('idx_schedules_confirmed', 'confirmed'),
    )

    @property
    def role_name(self):
        return self.role.role_name if self.role else None

    @property
    def member_name(self):
        return self.member.member_name if self.member else None


class RescheduleRequest(Base):
    """
    Member-submitted request to replace a previously published assignment.
    One schedule slot can only have one open request at a time.
    """
    __tablename__ = "reschedule_requests"

    request_id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("schedules.schedule_id", ondelete="CASCADE"), nullable=False)
    form_id = Column(Integer, ForeignKey("monthly_forms.form_id", ondelete="CASCADE"), nullable=False)
    service_week = Column(Integer, nullable=False)
    role_id = Column(Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False)
    requesting_member_id = Column(Integer, ForeignKey("members.member_id", ondelete="CASCADE"), nullable=False)
    original_member_id = Column(Integer, ForeignKey("members.member_id", ondelete="CASCADE"), nullable=False)
    reason = Column(String(1000), nullable=False)
    status = Column(
        Enum('open', 'applied', 'cancelled', 'rejected', name='reschedule_request_status'),
        default='open',
        nullable=False,
    )
    submitted_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    processed_note = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    schedule = relationship("Schedule")
    form = relationship("MonthlyForm")
    role = relationship("Role")
    requesting_member = relationship("Member", foreign_keys=[requesting_member_id])
    original_member = relationship("Member", foreign_keys=[original_member_id])
    candidates = relationship(
        "RescheduleRequestCandidate",
        back_populates="request",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index('idx_reschedule_requests_form_week', 'form_id', 'service_week'),
        Index('idx_reschedule_requests_status', 'status'),
        Index('idx_reschedule_requests_original_member', 'original_member_id'),
    )


class RescheduleRequestCandidate(Base):
    """
    Optional privately discussed replacement choices attached to a reschedule request.
    """
    __tablename__ = "reschedule_request_candidates"

    request_candidate_id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("reschedule_requests.request_id", ondelete="CASCADE"), nullable=False)
    member_id = Column(Integer, ForeignKey("members.member_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    request = relationship("RescheduleRequest", back_populates="candidates")
    member = relationship("Member")

    __table_args__ = (
        UniqueConstraint('request_id', 'member_id', name='unique_request_candidate_member'),
        Index('idx_reschedule_request_candidates_request', 'request_id'),
        Index('idx_reschedule_request_candidates_member', 'member_id'),
    )


class RoleConflict(Base):
    """
    Defines role combinations that cannot be assigned to the same member simultaneously.
    Purpose: Prevents scheduling conflicts (e.g., AV + Worship Leader same day).
    """
    __tablename__ = "role_conflicts"
    
    conflict_id = Column(Integer, primary_key=True)
    role_id_1 = Column(Integer, nullable=False)
    role_id_2 = Column(Integer, nullable=False)
    conflict_reason = Column(String(500), nullable=True)
    conflict_type = Column(Enum('strong', 'weak', name='conflict_type'), default='strong')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    role_1 = relationship("Role", foreign_keys=[role_id_1])
    role_2 = relationship("Role", foreign_keys=[role_id_2])
    
    __table_args__ = (
        ForeignKeyConstraint(['role_id_1'], ['roles.role_id'], ondelete='CASCADE'),
        ForeignKeyConstraint(['role_id_2'], ['roles.role_id'], ondelete='CASCADE'),
        UniqueConstraint('role_id_1', 'role_id_2', name='unique_role_pair'),
        Index('idx_role_conflicts_role1', 'role_id_1'),
        Index('idx_role_conflicts_role2', 'role_id_2'),
        Index('idx_role_conflicts_is_active', 'is_active'),
        Index('idx_role_conflicts_conflict_type', 'conflict_type'),
        CheckConstraint('role_id_1 < role_id_2', name='chk_role_order'),
    )


# =============================================================================
# Pydantic Models for API Request/Response
# =============================================================================

class MemberCreate(BaseModel):
    """Create a new member"""
    member_name: str
    member_gender: Optional[str] = None  # 'male' or 'female'
    email: Optional[str] = None
    phone: Optional[str] = None
    joined_date: Optional[date] = None
    bible_study_group: Optional[str] = None  # 'group_a' or 'group_b'
    is_senior_for_pairing: bool = False
    qualified_roles: Optional[List[int]] = None  # List of role_ids the member is qualified for


class MemberUpdate(BaseModel):
    """Update member details"""
    member_name: Optional[str] = None
    member_gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    bible_study_group: Optional[str] = None
    is_senior_for_pairing: Optional[bool] = None
    qualified_roles: Optional[List[int]] = None


class MemberResponse(BaseModel):
    """Full member details"""
    member_id: int
    member_name: str
    member_gender: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    is_active: bool
    joined_date: Optional[date]
    bible_study_group: Optional[str]
    is_senior_for_pairing: bool
    created_at: datetime
    updated_at: datetime


class RoleCreate(BaseModel):
    """Create a new role"""
    role_name: str
    description: Optional[str] = None
    people_needed: int = 1
    same_gender_required: bool = False


class RoleResponse(BaseModel):
    """Role details"""
    role_id: int
    role_name: str
    description: Optional[str]
    people_needed: int
    same_gender_required: bool


class MemberRoleCreate(BaseModel):
    """Assign a role qualification to a member"""
    member_id: int
    role_id: int
    notes: Optional[str] = None


class MemberRoleResponse(BaseModel):
    """Member role qualification details"""
    member_role_id: int
    member_id: int
    role_id: int
    role_name: str
    is_current: bool
    qualified_date: Optional[date]


class MemberWithRoles(BaseModel):
    """Member with all their qualified roles"""
    member_id: int
    member_name: str
    member_gender: Optional[str]
    email: Optional[str]
    is_active: bool
    bible_study_group: Optional[str]
    is_senior_for_pairing: bool
    roles: List[MemberRoleResponse] = []


class MonthlyFormCreate(BaseModel):
    """Create a new three-month service period form"""
    form_month: date
    service_weeks: Optional[int] = None
    submission_deadline: Optional[date] = None
    notes: Optional[str] = None


class MonthlyFormUpdate(BaseModel):
    """Update form status or details"""
    status: Optional[str] = None  # 'draft', 'open', 'closed', 'published'
    submission_deadline: Optional[date] = None
    notes: Optional[str] = None


class MonthlyFormResponse(BaseModel):
    """Full form details"""
    form_id: int
    form_month: date
    service_weeks: int
    submission_deadline: Optional[date]
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class ServiceDateCreate(BaseModel):
    """Create a service date mapping"""
    form_id: int
    service_week: int
    friday_date: date
    is_holiday: bool = False
    notes: Optional[str] = None


class ServiceDateUpdate(BaseModel):
    """Update service date (rarely needed)"""
    friday_date: Optional[date] = None
    is_holiday: Optional[bool] = None
    notes: Optional[str] = None


class ServiceDateResponse(BaseModel):
    """Service date details - calendar mapping for a week"""
    service_date_id: int
    form_id: int
    service_week: int
    friday_date: date
    is_holiday: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class AvailabilityEntryCreate(BaseModel):
    """Submit/update member availability"""
    week_1: Optional[bool] = None
    week_2: Optional[bool] = None
    week_3: Optional[bool] = None
    week_4: Optional[bool] = None
    week_5: Optional[bool] = None
    notes: Optional[str] = None


class AvailabilityEntryResponse(BaseModel):
    """Member's availability for a week"""
    availability_id: int
    form_id: int
    member_id: int
    service_week: int
    is_available: bool
    notes: Optional[str]
    submitted_at: Optional[datetime]


class ScheduleCreate(BaseModel):
    """Create a schedule assignment"""
    form_id: int
    service_week: int
    role_id: int
    assignment_slot: Optional[int] = None
    member_id: int
    notes: Optional[str] = None


class ScheduleUpdate(BaseModel):
    """Update an assignment"""
    confirmed: Optional[bool] = None
    notes: Optional[str] = None


class ScheduleResponse(BaseModel):
    """Full schedule assignment"""
    schedule_id: int
    form_id: int
    service_week: int
    role_id: int
    assignment_slot: int
    role_name: str
    member_id: int
    member_name: str
    notes: Optional[str]
    confirmed: bool
    created_at: datetime


class RescheduleRequestCreate(BaseModel):
    """Submit a request to replace an existing schedule assignment"""
    schedule_id: int
    requesting_member_id: int
    reason: str
    preferred_candidate_ids: Optional[List[int]] = None


class RescheduleRequestCandidateResponse(BaseModel):
    """Candidate member attached to a reschedule request"""
    member_id: int
    member_name: str


class RescheduleRequestResponse(BaseModel):
    """Reschedule request details"""
    request_id: int
    schedule_id: int
    form_id: int
    service_week: int
    role_id: int
    role_name: str
    requesting_member_id: int
    original_member_id: int
    original_member_name: str
    reason: str
    status: str
    submitted_at: datetime
    processed_at: Optional[datetime]
    processed_note: Optional[str]
    preferred_candidates: List[RescheduleRequestCandidateResponse] = []


class ReplacementCandidateResponse(BaseModel):
    """Available replacement option for a schedule assignment"""
    member_id: int
    member_name: str
    member_gender: Optional[str]
    bible_study_group: Optional[str]
    is_senior_for_pairing: bool
    served_previous_week_same_role: bool
    served_next_week_same_role: bool
    monthly_assignment_count: int


class WeeklyScheduleView(BaseModel):
    """View of all assignments for a specific week"""
    service_week: int
    assignments: List[ScheduleResponse] = []
    unassigned_critical_roles: List[str] = []  # Roles that must be filled


class MonthlyScheduleView(BaseModel):
    """Full month schedule overview"""
    form_id: int
    form_month: date
    weeks: List[WeeklyScheduleView] = []
    total_assignments: int
    unassigned_roles: int


class AvailabilityGap(BaseModel):
    """Report of who's missing for a role-week combo"""
    service_week: int
    role_id: int
    role_name: str
    is_critical: bool
    available_members: List[MemberResponse] = []
    unavailable_all: List[MemberResponse] = []


class RoleConflictCreate(BaseModel):
    """Create a new role conflict rule"""
    role_id_1: int
    role_id_2: int
    conflict_reason: Optional[str] = None
    conflict_type: str = "strong"  # 'strong' or 'weak'


class RoleConflictResponse(BaseModel):
    """Role conflict definition"""
    conflict_id: int
    role_id_1: int
    role_id_2: int
    role_1_name: str
    role_2_name: str
    conflict_reason: Optional[str]
    conflict_type: str
    is_active: bool
    created_at: datetime


class ScheduleConflictCheck(BaseModel):
    """Check if a proposed assignment would create conflicts"""
    proposed_member_id: int
    proposed_role_id: int
    service_week: int
    form_id: int
    would_conflict: bool
    conflicting_assignments: List[ScheduleResponse] = []


class FormStatusResponse(BaseModel):
    """Monthly form completion status"""
    form_id: int
    form_month: date
    status: str
    total_members: int
    responses_submitted: int
    response_rate: float
    deadline_approaching: bool


# =============================================================================
# Query Response Models (for complex views)
# =============================================================================

class MemberWorkload(BaseModel):
    """Track how many assignments each member has"""
    member_id: int
    member_name: str
    assignment_count: int
    assignments: List[str]  # List like "Worship (Week 1)", "AV (Week 3)"


class ScheduleConflict(BaseModel):
    """Potential issues in schedule"""
    conflict_type: str  # 'over_scheduled', 'unavailable_assigned', 'unqualified_assigned'
    member_id: int
    member_name: str
    role_id: int
    role_name: str
    service_week: int
    details: str


# Config for Pydantic models
class Config:
    from_attributes = True  # Allow model from SQLAlchemy ORM objects
    json_encoders = {
        datetime: lambda v: v.isoformat(),
        date: lambda v: v.isoformat(),
    }


# Export all models
__all__ = [
    'Member', 'Role', 'MemberRole', 'MonthlyForm', 'ServiceDate', 'AvailabilityEntry', 'Schedule',
    'RescheduleRequest', 'RescheduleRequestCandidate', 'RoleConflict',
    'MemberCreate', 'MemberUpdate', 'MemberResponse', 'MemberWithRoles',
    'RoleResponse',
    'MemberRoleCreate', 'MemberRoleResponse',
    'MonthlyFormCreate', 'MonthlyFormUpdate', 'MonthlyFormResponse', 'FormStatusResponse',
    'ServiceDateCreate', 'ServiceDateUpdate', 'ServiceDateResponse',
    'AvailabilityEntryCreate', 'AvailabilityEntryResponse',
    'ScheduleCreate', 'ScheduleUpdate', 'ScheduleResponse',
    'RescheduleRequestCreate', 'RescheduleRequestResponse', 'RescheduleRequestCandidateResponse',
    'ReplacementCandidateResponse',
    'WeeklyScheduleView', 'MonthlyScheduleView',
    'AvailabilityGap', 'RoleConflictCreate', 'RoleConflictResponse', 'ScheduleConflictCheck',
    'MemberWorkload', 'ScheduleConflict',
]
