"""Audit trail service — "who changed what", for security and compliance.

Deliberately separate from product analytics (services.analytics): audit answers
accountability questions, analytics answers usage questions. They never share a
store or a model.

Nothing secret is ever written: values for sensitive-looking keys are redacted
before a summary is produced.
"""

import logging
import uuid
from datetime import UTC, datetime

from greenlead.models.schemas import AuditEvent, User
from greenlead.repositories.base import AuditRepository

logger = logging.getLogger(__name__)

# Actions we record. Kept explicit so the admin filter can offer a real list.
ACTIONS = (
    "auth.login_success",
    "auth.login_failed",
    "auth.logout",
    "user.create",
    "user.activate",
    "user.deactivate",
    "user.role_change",
    "company.create",
    "company.update",
    "company.archive",
    "company.reassign",
    "contact.create",
    "contact.update",
    "contact.delete",
    "contact.decision_maker_change",
    "followup.create",
    "followup.complete",
    "followup.cancel",
    "meeting.create",
    "meeting.update",
    "meeting.complete",
    "meeting.cancel",
    "authz.denied",
)

# Keys whose values must never reach the audit trail.
_SENSITIVE = (
    "password",
    "password_hash",
    "token",
    "secret",
    "api_key",
    "apikey",
    "credential",
    "session",
    "authorization",
)


def redact(data: dict[str, object]) -> dict[str, object]:
    """Return a copy with sensitive values replaced by a placeholder."""
    out: dict[str, object] = {}
    for key, value in data.items():
        if any(marker in key.lower() for marker in _SENSITIVE):
            out[key] = "[redacted]"
        else:
            out[key] = value
    return out


def summarize(changes: dict[str, object] | None) -> str:
    """Render a short, safe ``key=value`` summary (values truncated)."""
    if not changes:
        return ""
    parts = []
    for key, value in redact(changes).items():
        text = str(value)
        if len(text) > 80:
            text = text[:77] + "..."
        parts.append(f"{key}={text}")
    return "; ".join(parts)


class AuditService:
    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    def record(
        self,
        action: str,
        actor: User | None = None,
        actor_username: str = "",
        entity_type: str = "",
        entity_id: str = "",
        outcome: str = "success",
        changes: dict[str, object] | None = None,
        reason: str = "",
        correlation_id: str = "",
    ) -> AuditEvent:
        """Append one audit event. Never raises into the caller's flow."""
        event = AuditEvent(
            id=str(uuid.uuid4()),
            actor_user_id=actor.id if actor else "",
            actor_username=actor.username if actor else actor_username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            timestamp=datetime.now(UTC).isoformat(),
            correlation_id=correlation_id,
            outcome=outcome,
            summary=summarize(changes),
            reason=reason,
        )
        try:
            return self._repo.append(event)
        except Exception as exc:  # noqa: BLE001
            # An audit write must never break a user-facing operation, but it
            # must be loud in the logs.
            logger.error("Failed to write audit event %s: %s", action, exc)
            return event

    def list_events(
        self,
        actor: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        return self._repo.list_events(
            actor=actor,
            action=action,
            entity_type=entity_type,
            outcome=outcome,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    def count_events(
        self,
        actor: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        return self._repo.count_events(
            actor=actor,
            action=action,
            entity_type=entity_type,
            outcome=outcome,
            date_from=date_from,
            date_to=date_to,
        )
