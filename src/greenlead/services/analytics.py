"""Product analytics service — "how is the product used".

Provider-independent by design: events are stored internally through this
service boundary. Shipping to Mixpanel/Amplitude later means adding an adapter
behind :class:`AnalyticsService`, not changing any call site.

Never mixed with the audit trail (services.audit), which answers a different,
security-oriented question.
"""

import json
import logging
import uuid
from datetime import UTC, datetime

from greenlead.models.schemas import ProductEvent
from greenlead.repositories.base import ProductEventRepository

logger = logging.getLogger(__name__)

# Canonical event names.
LOGIN_SUCCESS = "login_success"
COMPANY_CREATED = "company_created"
CONTACT_CREATED = "contact_created"
DECISION_MAKER_ADDED = "decision_maker_added"
FOLLOWUP_CREATED = "followup_created"
FOLLOWUP_COMPLETED = "followup_completed"
FOLLOWUP_OVERDUE = "followup_overdue"
MEETING_CREATED = "meeting_created"
MEETING_OUTCOME_ADDED = "meeting_outcome_added"
ATTENTION_ITEM_OPENED = "attention_item_opened"
ATTENTION_ITEM_RESOLVED = "attention_item_resolved"
SEARCH_USED = "search_used"

EVENT_NAMES = (
    LOGIN_SUCCESS,
    COMPANY_CREATED,
    CONTACT_CREATED,
    DECISION_MAKER_ADDED,
    FOLLOWUP_CREATED,
    FOLLOWUP_COMPLETED,
    FOLLOWUP_OVERDUE,
    MEETING_CREATED,
    MEETING_OUTCOME_ADDED,
    ATTENTION_ITEM_OPENED,
    ATTENTION_ITEM_RESOLVED,
    SEARCH_USED,
)


class AnalyticsService:
    def __init__(self, repo: ProductEventRepository) -> None:
        self._repo = repo

    def track(
        self,
        name: str,
        user_id: str = "",
        properties: dict[str, object] | None = None,
    ) -> ProductEvent:
        """Record one product event. Never raises into the caller's flow."""
        event = ProductEvent(
            id=str(uuid.uuid4()),
            name=name,
            user_id=user_id,
            timestamp=datetime.now(UTC).isoformat(),
            properties=json.dumps(properties or {}, ensure_ascii=False),
        )
        try:
            return self._repo.append(event)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write product event %s: %s", name, exc)
            return event

    def list_events(
        self, name: str | None = None, limit: int = 200
    ) -> list[ProductEvent]:
        return self._repo.list_events(name=name, limit=limit)

    def counts(self) -> dict[str, int]:
        return self._repo.count_by_name()
