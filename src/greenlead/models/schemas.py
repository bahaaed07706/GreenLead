"""Domain models for GreenLead entities.

These Pydantic models define the data contracts between the repository layer
and the rest of the application. They are independent of any storage backend.
"""

from pydantic import BaseModel, Field


class User(BaseModel):
    """An application user with a role. Password hashes are never exposed here."""

    id: str = Field(..., description="UUID identifier")
    username: str = Field(..., min_length=1, description="Unique login username")
    name: str = Field(default="", description="Display name")
    email: str = Field(default="", description="Email address")
    role: str = Field(default="employee", description="employee | manager | admin")
    is_active: bool = Field(default=True, description="Whether the account is active")
    last_login: str | None = Field(default=None, description="ISO timestamp")
    created_at: str = Field(default="", description="ISO timestamp of creation")
    updated_at: str = Field(default="", description="ISO timestamp of last update")
    created_by: str = Field(default="", description="Username of creator")


class UserCreate(BaseModel):
    """Input model for creating a user (plaintext password is hashed by service)."""

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    name: str = Field(default="")
    email: str = Field(default="")
    role: str = Field(default="employee")
    created_by: str = Field(default="")


class Company(BaseModel):
    """A company record in the GreenLead pipeline."""

    id: str = Field(..., description="UUID identifier")
    name_en: str = Field(..., min_length=1, description="English company name")
    name_ar: str = Field(default="", description="Arabic company name")
    domain: str = Field(default="", description="Normalized website domain")
    sector: str = Field(default="", description="Industry sector")
    city: str = Field(default="", description="City location")
    description: str = Field(default="", description="Company description")
    products: str = Field(default="", description="Products/services offered")
    digital_footprint: str = Field(default="", description="Digital presence notes")
    compliance_status: str = Field(default="", description="Compliance status")
    fit_score: float = Field(default=0.0, description="Fit score 0-100")
    confidence_score: float = Field(default=0.0, description="Confidence score 0-100")
    created_at: str = Field(default="", description="ISO timestamp of creation")
    updated_at: str = Field(default="", description="ISO timestamp of last update")
    archived_at: str | None = Field(
        default=None, description="ISO timestamp if archived"
    )
    verification_status: str = Field(
        default="unverified", description="Verification status"
    )
    # Accountability. owner_id is authoritative for record-level authorization;
    # empty means unassigned (visible to manager/admin only).
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")
    updated_by_id: str = Field(default="", description="User.id of last update")


class CompanyCreate(BaseModel):
    """Input model for creating a new company."""

    name_en: str = Field(..., min_length=1)
    name_ar: str = Field(default="")
    domain: str = Field(default="")
    sector: str = Field(default="")
    city: str = Field(default="")
    description: str = Field(default="")
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")


class Contact(BaseModel):
    """A contact record associated with a company."""

    id: str = Field(..., description="UUID identifier")
    company_id: str = Field(..., description="Foreign key UUID to Company")
    name: str = Field(..., min_length=1, description="Full name of contact")
    title: str = Field(default="", description="Job title / role")
    email: str = Field(default="", description="Email address")
    phone: str = Field(default="", description="Phone number")
    relationship_level: str = Field(
        default="Contact",
        description="Relationship level e.g. Decision Maker, Influencer",
    )
    is_decision_maker: bool = Field(
        default=False, description="Flag indicating if contact is a decision maker"
    )
    source_url: str = Field(
        default="", description="Source URL where contact was found"
    )
    verification_status: str = Field(
        default="unverified", description="Verification status"
    )
    notes: str = Field(default="", description="Additional notes")
    created_at: str = Field(default="", description="ISO timestamp of creation")
    updated_at: str = Field(default="", description="ISO timestamp of last update")
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")
    updated_by_id: str = Field(default="", description="User.id of last update")


class ContactCreate(BaseModel):
    """Input model for creating a new contact."""

    company_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    title: str = Field(default="")
    email: str = Field(default="")
    phone: str = Field(default="")
    relationship_level: str = Field(default="Contact")
    is_decision_maker: bool = Field(default=False)
    source_url: str = Field(default="")
    notes: str = Field(default="")
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")


class ContactUpdate(BaseModel):
    """Input model for updating an existing contact."""

    name: str | None = Field(default=None)
    title: str | None = Field(default=None)
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    relationship_level: str | None = Field(default=None)
    is_decision_maker: str | bool | None = Field(default=None)
    source_url: str | None = Field(default=None)
    notes: str | None = Field(default=None)


class FollowUp(BaseModel):
    """A follow-up task tied to a company (and optionally a contact).

    Stored status is one of Pending | In Progress | Completed | Cancelled.
    The "Overdue" state is derived (active status + due_date in the past),
    never stored, so it stays correct as time passes.
    """

    id: str = Field(..., description="UUID identifier")
    company_id: str = Field(..., description="FK to Company")
    contact_id: str = Field(default="", description="Optional FK to Contact")
    title: str = Field(..., min_length=1, description="Follow-up task title")
    description: str = Field(default="", description="Task details")
    due_date: str = Field(default="", description="ISO date YYYY-MM-DD")
    priority: str = Field(default="Medium", description="High | Medium | Low")
    status: str = Field(
        default="Pending",
        description="Pending | In Progress | Completed | Cancelled",
    )
    owner: str = Field(default="", description="Owner username (display only)")
    outcome: str = Field(default="", description="Outcome recorded on completion")
    completed_at: str | None = Field(default=None, description="ISO completion time")
    created_at: str = Field(default="", description="ISO timestamp of creation")
    updated_at: str = Field(default="", description="ISO timestamp of last update")
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")
    updated_by_id: str = Field(default="", description="User.id of last update")


class FollowUpCreate(BaseModel):
    """Input model for creating a follow-up."""

    company_id: str = Field(..., min_length=1)
    contact_id: str = Field(default="")
    title: str = Field(..., min_length=1)
    description: str = Field(default="")
    due_date: str = Field(default="")
    priority: str = Field(default="Medium")
    owner: str = Field(default="")
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")


class FollowUpUpdate(BaseModel):
    """Input model for updating a follow-up."""

    title: str | None = Field(default=None)
    description: str | None = Field(default=None)
    due_date: str | None = Field(default=None)
    priority: str | None = Field(default=None)
    status: str | None = Field(default=None)
    outcome: str | None = Field(default=None)
    completed_at: str | None = Field(default=None)


class Meeting(BaseModel):
    """A scheduled meeting tied to a company (and optionally a contact).

    Stored status is Scheduled | Completed | Cancelled | No Show. Times are
    stored as zero-padded ``HH:MM`` strings in the meeting's ``timezone``.
    """

    id: str = Field(..., description="UUID identifier")
    company_id: str = Field(..., description="FK to Company")
    contact_id: str = Field(default="", description="Optional FK to Contact")
    subject: str = Field(..., min_length=1, description="Meeting subject")
    description: str = Field(default="", description="Meeting description")
    meeting_date: str = Field(default="", description="ISO date YYYY-MM-DD")
    start_time: str = Field(default="", description="HH:MM (24h)")
    end_time: str = Field(default="", description="HH:MM (24h)")
    timezone: str = Field(default="Asia/Riyadh", description="IANA timezone name")
    meeting_type: str = Field(
        default="Online", description="Online | In Person | Phone"
    )
    meeting_url: str = Field(default="", description="Video URL for online meetings")
    location: str = Field(default="", description="Address for in-person meetings")
    participants: str = Field(default="", description="Comma-separated participants")
    agenda: str = Field(default="", description="Meeting agenda")
    reminder_minutes: int = Field(default=30, description="Reminder lead time (min)")
    status: str = Field(
        default="Scheduled",
        description="Scheduled | Completed | Cancelled | No Show",
    )
    outcome: str = Field(default="", description="Outcome recorded after the meeting")
    followup_action: str = Field(default="", description="Next action after meeting")
    owner: str = Field(default="", description="Owner username (display only)")
    created_at: str = Field(default="", description="ISO timestamp of creation")
    updated_at: str = Field(default="", description="ISO timestamp of last update")
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")
    updated_by_id: str = Field(default="", description="User.id of last update")


class MeetingCreate(BaseModel):
    """Input model for creating a meeting."""

    company_id: str = Field(..., min_length=1)
    contact_id: str = Field(default="")
    subject: str = Field(..., min_length=1)
    description: str = Field(default="")
    meeting_date: str = Field(default="")
    start_time: str = Field(default="")
    end_time: str = Field(default="")
    timezone: str = Field(default="Asia/Riyadh")
    meeting_type: str = Field(default="Online")
    meeting_url: str = Field(default="")
    location: str = Field(default="")
    participants: str = Field(default="")
    agenda: str = Field(default="")
    reminder_minutes: int = Field(default=30)
    owner: str = Field(default="")
    owner_id: str = Field(default="", description="User.id accountable for record")
    created_by_id: str = Field(default="", description="User.id that created it")


class MeetingUpdate(BaseModel):
    """Input model for updating a meeting."""

    subject: str | None = Field(default=None)
    description: str | None = Field(default=None)
    meeting_date: str | None = Field(default=None)
    start_time: str | None = Field(default=None)
    end_time: str | None = Field(default=None)
    timezone: str | None = Field(default=None)
    meeting_type: str | None = Field(default=None)
    meeting_url: str | None = Field(default=None)
    location: str | None = Field(default=None)
    participants: str | None = Field(default=None)
    agenda: str | None = Field(default=None)
    reminder_minutes: int | None = Field(default=None)
    status: str | None = Field(default=None)
    outcome: str | None = Field(default=None)
    followup_action: str | None = Field(default=None)


class AuditEvent(BaseModel):
    """An append-oriented security/business audit record.

    Never carries passwords, API keys, session tokens or full credential
    payloads — only a short, human-readable ``summary`` of what changed.
    """

    id: str = Field(..., description="UUID identifier")
    actor_user_id: str = Field(default="", description="User.id of the actor")
    actor_username: str = Field(default="", description="Username of the actor")
    action: str = Field(..., description="e.g. company.create, auth.login_failed")
    entity_type: str = Field(default="", description="Company | Contact | User | ...")
    entity_id: str = Field(default="", description="Affected record identifier")
    timestamp: str = Field(default="", description="ISO timestamp (UTC)")
    correlation_id: str = Field(default="", description="Per-request correlation id")
    outcome: str = Field(default="success", description="success | denied | failure")
    summary: str = Field(default="", description="Safe before/after summary")
    reason: str = Field(default="", description="Reason, when required")


class ProductEvent(BaseModel):
    """A product-analytics event. Deliberately separate from AuditEvent.

    Audit answers "who changed what" for security/compliance; product events
    answer "how is the product used" for analytics. They are never merged.
    """

    id: str = Field(..., description="UUID identifier")
    name: str = Field(..., description="e.g. company_created, search_used")
    user_id: str = Field(default="", description="User.id that triggered it")
    timestamp: str = Field(default="", description="ISO timestamp (UTC)")
    properties: str = Field(default="", description="JSON string of safe properties")


class StorageStatus(BaseModel):
    """Safe storage status summary using explicit 4-state integration model."""

    state: str = Field(
        ...,
        description="not_configured | configured_unverified | live_verified | error",
    )
    backend_type: str = Field(..., description="in_memory | google_sheets")
    status_label_en: str = Field(...)
    status_label_ar: str = Field(...)
    details_en: str = Field(...)
    details_ar: str = Field(...)


class ResearchStatus(BaseModel):
    """Safe research pipeline status summary using explicit 4-state integration model."""

    state: str = Field(
        ...,
        description="not_configured | configured_unverified | live_verified | error",
    )
    provider_type: str = Field(..., description="mock | tavily | ai")
    status_label_en: str = Field(...)
    status_label_ar: str = Field(...)
    details_en: str = Field(...)
    details_ar: str = Field(...)


class WorkQueueItem(BaseModel):
    """An actionable record-level item in the Needs Attention Work Queue."""

    id: str = Field(..., description="Unique queue item identifier")
    record_id: str = Field(..., description="ID of associated Company or Contact")
    record_name: str = Field(..., description="Display name of Company or Contact")
    record_type: str = Field(..., description="Company | Contact")
    issue_title_en: str = Field(...)
    issue_title_ar: str = Field(...)
    explanation_en: str = Field(...)
    explanation_ar: str = Field(...)
    severity: str = Field(..., description="high | medium | low")
    link_url: str = Field(..., description="Direct link to company or contact workflow")
    action_label_en: str = Field(...)
    action_label_ar: str = Field(...)


class DashboardSummary(BaseModel):
    """Aggregated operational metrics for the GreenLead dashboard."""

    total_companies: int = 0
    total_contacts: int = 0
    decision_makers_count: int = 0
    verified_contacts_count: int = 0
    unverified_contacts_count: int = 0
    companies_without_contacts_count: int = 0
    companies_without_decision_maker_count: int = 0
    contacts_missing_source_url_count: int = 0
    # Today view (derived from follow-ups; more entity types added in later phases)
    overdue_followups_count: int = 0
    followups_due_today_count: int = 0
    upcoming_followups_count: int = 0
    today_followups: list[FollowUp] = Field(default_factory=list)
    overdue_followups: list[FollowUp] = Field(default_factory=list)
    meetings_today_count: int = 0
    upcoming_meetings_count: int = 0
    meetings_missing_outcome_count: int = 0
    meetings_today: list[Meeting] = Field(default_factory=list)
    next_meeting: Meeting | None = None
    work_queue: list[WorkQueueItem] = Field(default_factory=list)
    sectors_breakdown: dict[str, int] = Field(default_factory=dict)
    relationship_breakdown: dict[str, int] = Field(default_factory=dict)
    recent_companies: list[Company] = Field(default_factory=list)
    recent_contacts: list[Contact] = Field(default_factory=list)
    storage_status: StorageStatus
    research_status: ResearchStatus
    ai_status: ResearchStatus
