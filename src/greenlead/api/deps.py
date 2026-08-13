"""Shared route dependencies / service builders.

Keeps audit and analytics wiring in one place so routes don't each re-import
the repositories.
"""

from greenlead.repositories import (
    get_audit_repository,
    get_product_event_repository,
)
from greenlead.services.analytics import AnalyticsService
from greenlead.services.audit import AuditService


def audit_service() -> AuditService:
    return AuditService(get_audit_repository())


def analytics_service() -> AnalyticsService:
    return AnalyticsService(get_product_event_repository())
