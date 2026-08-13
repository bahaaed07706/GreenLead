"""Meeting business service.

Owns meeting lifecycle (schedule, complete, cancel, no-show), validation, the
Today/Upcoming/missing-outcome derivations used by the dashboard, and a minimal
standards-compliant iCalendar (.ics) export.

Date logic accepts an injectable ``today`` so it is fully testable.
"""

import logging
from datetime import UTC, date, datetime
from typing import Any

from greenlead.core import policy
from greenlead.models.schemas import Meeting, MeetingCreate, User
from greenlead.repositories.base import (
    CompanyRepository,
    ContactRepository,
    MeetingRepository,
)

logger = logging.getLogger(__name__)

VALID_TYPES = frozenset({"Online", "In Person", "Phone"})
VALID_STATUSES = frozenset({"Scheduled", "Completed", "Cancelled", "No Show"})
ACTIVE_STATUSES = frozenset({"Scheduled"})


def parse_date(value: str) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` date, returning None if empty/invalid."""
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _valid_hhmm(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return 0 <= h <= 23 and 0 <= m <= 59


def is_today(meeting: Meeting, today: date) -> bool:
    d = parse_date(meeting.meeting_date)
    return meeting.status in ACTIVE_STATUSES and d is not None and d == today


def is_upcoming(meeting: Meeting, today: date) -> bool:
    d = parse_date(meeting.meeting_date)
    return meeting.status in ACTIVE_STATUSES and d is not None and d > today


def is_missing_outcome(meeting: Meeting, today: date) -> bool:
    """A meeting whose date has passed but is still Scheduled with no outcome."""
    d = parse_date(meeting.meeting_date)
    return (
        meeting.status == "Scheduled"
        and d is not None
        and d < today
        and not meeting.outcome.strip()
    )


def _sort_key(meeting: Meeting) -> tuple[str, str]:
    return (meeting.meeting_date or "9999-12-31", meeting.start_time or "99:99")


class MeetingService:
    def __init__(
        self,
        meeting_repo: MeetingRepository,
        company_repo: CompanyRepository,
        contact_repo: ContactRepository | None = None,
    ) -> None:
        self._meeting_repo = meeting_repo
        self._company_repo = company_repo
        self._contact_repo = contact_repo

    def list_meetings(self, company_id: str | None = None) -> list[Meeting]:
        return sorted(self._meeting_repo.list_meetings(company_id), key=_sort_key)

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        return self._meeting_repo.get_meeting(meeting_id)

    def _validate(self, data: MeetingCreate) -> None:
        company = self._company_repo.get_company(data.company_id)
        if not company:
            raise KeyError(f"Company not found: {data.company_id}")
        if not data.subject.strip():
            raise ValueError("Meeting subject is required.")
        if data.meeting_type not in VALID_TYPES:
            raise ValueError(f"Invalid meeting type: {data.meeting_type}")
        if data.contact_id and self._contact_repo is not None:
            contact = self._contact_repo.get_contact(data.contact_id)
            if contact is None or contact.company_id != data.company_id:
                raise ValueError("Contact does not belong to the selected company.")
        if data.meeting_type == "Online" and not data.meeting_url.strip():
            raise ValueError("Online meetings require a meeting URL.")
        if data.meeting_type == "In Person" and not data.location.strip():
            raise ValueError("In-person meetings require a location.")
        if data.meeting_date and parse_date(data.meeting_date) is None:
            raise ValueError(f"Invalid meeting date: {data.meeting_date}")
        for t in (data.start_time, data.end_time):
            if t and not _valid_hhmm(t):
                raise ValueError(f"Invalid time: {t}")
        if (
            data.start_time
            and data.end_time
            and _valid_hhmm(data.start_time)
            and _valid_hhmm(data.end_time)
            and data.end_time <= data.start_time
        ):
            raise ValueError("End time must be after start time.")

    def create_meeting(self, data: MeetingCreate) -> Meeting:
        self._validate(data)
        meeting = self._meeting_repo.create_meeting(data)
        logger.info(
            "Meeting created: %s for company %s", meeting.subject, data.company_id
        )
        return meeting

    def update_meeting(self, meeting_id: str, data: dict[str, Any]) -> Meeting:
        existing = self._meeting_repo.get_meeting(meeting_id)
        if not existing:
            raise KeyError(f"Meeting not found: {meeting_id}")
        if "status" in data and data["status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {data['status']}")
        return self._meeting_repo.update_meeting(meeting_id, data)

    def complete_meeting(
        self, meeting_id: str, outcome: str = "", followup_action: str = ""
    ) -> Meeting:
        return self.update_meeting(
            meeting_id,
            {
                "status": "Completed",
                "outcome": outcome,
                "followup_action": followup_action,
            },
        )

    def cancel_meeting(self, meeting_id: str) -> Meeting:
        return self.update_meeting(meeting_id, {"status": "Cancelled"})

    def delete_meeting(self, meeting_id: str) -> bool:
        return self._meeting_repo.delete_meeting(meeting_id)

    # ── Today-view derivations ──────────────────────────────────────────────

    def today(self, today: date | None = None) -> list[Meeting]:
        ref = today or datetime.now(UTC).date()
        return sorted(
            (m for m in self._meeting_repo.list_meetings() if is_today(m, ref)),
            key=_sort_key,
        )

    def upcoming(self, today: date | None = None) -> list[Meeting]:
        ref = today or datetime.now(UTC).date()
        return sorted(
            (m for m in self._meeting_repo.list_meetings() if is_upcoming(m, ref)),
            key=_sort_key,
        )

    def missing_outcome(self, today: date | None = None) -> list[Meeting]:
        ref = today or datetime.now(UTC).date()
        return sorted(
            (
                m
                for m in self._meeting_repo.list_meetings()
                if is_missing_outcome(m, ref)
            ),
            key=_sort_key,
        )

    # ── Authorized API (routes) ─────────────────────────────────────────────

    def _parent_owner(self, company_id: str) -> str:
        company = self._company_repo.get_company(company_id)
        return company.owner_id if company else ""

    def _visible(self, actor: User, items: list[Meeting]) -> list[Meeting]:
        return policy.filter_visible_related(
            actor, [(m, self._parent_owner(m.company_id)) for m in items]
        )

    def list_meetings_for(
        self, actor: User, company_id: str | None = None
    ) -> list[Meeting]:
        return self._visible(actor, self.list_meetings(company_id))

    def today_for(self, actor: User, today: date | None = None) -> list[Meeting]:
        return self._visible(actor, self.today(today))

    def upcoming_for(self, actor: User, today: date | None = None) -> list[Meeting]:
        return self._visible(actor, self.upcoming(today))

    def get_meeting_for(self, actor: User, meeting_id: str) -> Meeting:
        item = self._meeting_repo.get_meeting(meeting_id)
        if item is None:
            raise KeyError(f"Meeting not found: {meeting_id}")
        policy.require_view_related(
            actor, item.owner_id, self._parent_owner(item.company_id)
        )
        return item

    def create_meeting_for(self, actor: User, data: MeetingCreate) -> Meeting:
        policy.require_edit(actor, self._parent_owner(data.company_id))
        owned = data.model_copy(
            update={
                "owner_id": actor.id,
                "created_by_id": actor.id,
                "owner": actor.username,
            }
        )
        return self.create_meeting(owned)

    def complete_meeting_for(
        self, actor: User, meeting_id: str, outcome: str = "", followup_action: str = ""
    ) -> Meeting:
        self.get_meeting_for(actor, meeting_id)  # enforces access
        return self.complete_meeting(
            meeting_id, outcome=outcome, followup_action=followup_action
        )

    def cancel_meeting_for(self, actor: User, meeting_id: str) -> Meeting:
        self.get_meeting_for(actor, meeting_id)  # enforces access
        return self.cancel_meeting(meeting_id)

    def delete_meeting_for(self, actor: User, meeting_id: str) -> bool:
        self.get_meeting_for(actor, meeting_id)  # enforces access
        return self.delete_meeting(meeting_id)

    def next_meeting(self, today: date | None = None) -> Meeting | None:
        ref = today or datetime.now(UTC).date()
        candidates = self.today(ref) + self.upcoming(ref)
        return candidates[0] if candidates else None

    def to_ics(self, meeting: Meeting) -> str:
        """Render a minimal RFC 5545 VEVENT for calendar import.

        Times are emitted as floating local time (no TZID/UTC conversion) to
        avoid misrepresenting the zone; the stored timezone is noted in the
        description. Returns an empty-event calendar if date/times are missing.
        """

        def esc(text: str) -> str:
            return (
                text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\n", "\\n")
            )

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//GreenLead//Meetings//EN",
            "BEGIN:VEVENT",
            f"UID:{meeting.id}@greenlead",
            f"SUMMARY:{esc(meeting.subject)}",
        ]
        d = parse_date(meeting.meeting_date)
        if d and _valid_hhmm(meeting.start_time):
            stamp = (
                d.strftime("%Y%m%d") + "T" + meeting.start_time.replace(":", "") + "00"
            )
            lines.append(f"DTSTART:{stamp}")
        if d and _valid_hhmm(meeting.end_time):
            stamp = (
                d.strftime("%Y%m%d") + "T" + meeting.end_time.replace(":", "") + "00"
            )
            lines.append(f"DTEND:{stamp}")
        location = meeting.meeting_url or meeting.location
        if location:
            lines.append(f"LOCATION:{esc(location)}")
        desc_bits = [meeting.description, f"Timezone: {meeting.timezone}"]
        lines.append("DESCRIPTION:" + esc(" | ".join(b for b in desc_bits if b)))
        lines.extend(["END:VEVENT", "END:VCALENDAR"])
        return "\r\n".join(lines) + "\r\n"
