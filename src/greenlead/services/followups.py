"""Follow-up task business service.

Sits between routes and the repository layer. Owns follow-up lifecycle
(create, complete, cancel) and the deterministic date derivations used by the
dashboard Today view (overdue / due-today / upcoming).

Date logic accepts an injectable ``today`` so it is fully testable without
depending on the wall clock.
"""

import logging
from datetime import UTC, date, datetime
from typing import Any

from greenlead.core import policy
from greenlead.models.schemas import FollowUp, FollowUpCreate, User
from greenlead.repositories.base import CompanyRepository, FollowUpRepository

logger = logging.getLogger(__name__)

# Statuses that still require action (i.e. can be overdue / due today).
ACTIVE_STATUSES = frozenset({"Pending", "In Progress"})
VALID_STATUSES = frozenset({"Pending", "In Progress", "Completed", "Cancelled"})
VALID_PRIORITIES = frozenset({"High", "Medium", "Low"})


def parse_due_date(due_date: str) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` due date, returning None if empty/invalid."""
    if not due_date or not due_date.strip():
        return None
    try:
        return date.fromisoformat(due_date.strip()[:10])
    except ValueError:
        return None


def is_active(followup: FollowUp) -> bool:
    """True if the follow-up still needs action."""
    return followup.status in ACTIVE_STATUSES


def is_overdue(followup: FollowUp, today: date) -> bool:
    """True if an active follow-up's due date is strictly before ``today``."""
    due = parse_due_date(followup.due_date)
    return is_active(followup) and due is not None and due < today


def is_due_today(followup: FollowUp, today: date) -> bool:
    """True if an active follow-up is due exactly on ``today``."""
    due = parse_due_date(followup.due_date)
    return is_active(followup) and due is not None and due == today


def is_upcoming(followup: FollowUp, today: date) -> bool:
    """True if an active follow-up is due after ``today``."""
    due = parse_due_date(followup.due_date)
    return is_active(followup) and due is not None and due > today


class FollowUpService:
    def __init__(
        self,
        followup_repo: FollowUpRepository,
        company_repo: CompanyRepository,
    ) -> None:
        self._followup_repo = followup_repo
        self._company_repo = company_repo

    def list_followups(self, company_id: str | None = None) -> list[FollowUp]:
        """List follow-ups, optionally scoped to a company, newest due first."""
        items = self._followup_repo.list_followups(company_id)
        # Sort by due date ascending so the most imminent work surfaces first;
        # blank due dates sort last.
        return sorted(items, key=lambda f: f.due_date or "9999-12-31")

    def get_followup(self, followup_id: str) -> FollowUp | None:
        return self._followup_repo.get_followup(followup_id)

    def create_followup(self, data: FollowUpCreate) -> FollowUp:
        """Create a follow-up after validating the parent company and inputs."""
        company = self._company_repo.get_company(data.company_id)
        if not company:
            raise KeyError(f"Company not found: {data.company_id}")
        if not data.title.strip():
            raise ValueError("Follow-up title is required.")
        if data.priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {data.priority}")
        if parse_due_date(data.due_date) is None and data.due_date.strip():
            raise ValueError(f"Invalid due date: {data.due_date}")

        followup = self._followup_repo.create_followup(data)
        logger.info(
            "Follow-up created: %s for company %s", followup.title, data.company_id
        )
        return followup

    def update_followup(self, followup_id: str, data: dict[str, Any]) -> FollowUp:
        existing = self._followup_repo.get_followup(followup_id)
        if not existing:
            raise KeyError(f"Follow-up not found: {followup_id}")
        if "status" in data and data["status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {data['status']}")
        return self._followup_repo.update_followup(followup_id, data)

    def complete_followup(self, followup_id: str, outcome: str = "") -> FollowUp:
        """Mark a follow-up completed and stamp the completion time."""
        return self.update_followup(
            followup_id,
            {
                "status": "Completed",
                "outcome": outcome,
                "completed_at": datetime.now(UTC).isoformat(),
            },
        )

    def cancel_followup(self, followup_id: str) -> FollowUp:
        return self.update_followup(followup_id, {"status": "Cancelled"})

    def delete_followup(self, followup_id: str) -> bool:
        success = self._followup_repo.delete_followup(followup_id)
        if success:
            logger.info("Follow-up deleted: %s", followup_id)
        return success

    # ── Today-view derivations ──────────────────────────────────────────────

    def overdue(self, today: date | None = None) -> list[FollowUp]:
        ref = today or datetime.now(UTC).date()
        return [f for f in self._followup_repo.list_followups() if is_overdue(f, ref)]

    def due_today(self, today: date | None = None) -> list[FollowUp]:
        ref = today or datetime.now(UTC).date()
        return [f for f in self._followup_repo.list_followups() if is_due_today(f, ref)]

    def upcoming(self, today: date | None = None) -> list[FollowUp]:
        ref = today or datetime.now(UTC).date()
        return [f for f in self._followup_repo.list_followups() if is_upcoming(f, ref)]

    # ── Authorized API (routes) ─────────────────────────────────────────────

    def _parent_owner(self, company_id: str) -> str:
        company = self._company_repo.get_company(company_id)
        return company.owner_id if company else ""

    def list_followups_for(
        self, actor: User, company_id: str | None = None
    ) -> list[FollowUp]:
        items = self.list_followups(company_id)
        return policy.filter_visible_related(
            actor, [(f, self._parent_owner(f.company_id)) for f in items]
        )

    def get_followup_for(self, actor: User, followup_id: str) -> FollowUp:
        item = self._followup_repo.get_followup(followup_id)
        if item is None:
            raise KeyError(f"Follow-up not found: {followup_id}")
        policy.require_view_related(
            actor, item.owner_id, self._parent_owner(item.company_id)
        )
        return item

    def create_followup_for(self, actor: User, data: FollowUpCreate) -> FollowUp:
        policy.require_edit(actor, self._parent_owner(data.company_id))
        owned = data.model_copy(
            update={
                "owner_id": actor.id,
                "created_by_id": actor.id,
                "owner": actor.username,
            }
        )
        return self.create_followup(owned)

    def complete_followup_for(
        self, actor: User, followup_id: str, outcome: str = ""
    ) -> FollowUp:
        self.get_followup_for(actor, followup_id)  # enforces access
        return self.complete_followup(followup_id, outcome=outcome)

    def delete_followup_for(self, actor: User, followup_id: str) -> bool:
        self.get_followup_for(actor, followup_id)  # enforces access
        return self.delete_followup(followup_id)
