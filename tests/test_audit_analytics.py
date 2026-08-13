"""Audit Log and Product Analytics tests, including secrecy and separation."""

from greenlead.models.schemas import User
from greenlead.repositories.memory import (
    InMemoryAuditRepository,
    InMemoryProductEventRepository,
)
from greenlead.services.analytics import (
    COMPANY_CREATED,
    LOGIN_SUCCESS,
    AnalyticsService,
)
from greenlead.services.audit import AuditService, redact, summarize

ACTOR = User(id="u1", username="alice", role="employee")


def _audit() -> AuditService:
    return AuditService(InMemoryAuditRepository())


def _analytics() -> AnalyticsService:
    return AnalyticsService(InMemoryProductEventRepository())


def test_audit_record_and_list() -> None:
    svc = _audit()
    svc.record("company.create", actor=ACTOR, entity_type="Company", entity_id="c1")
    events = svc.list_events()
    assert len(events) == 1
    e = events[0]
    assert e.action == "company.create"
    assert e.actor_username == "alice"
    assert e.entity_id == "c1"
    assert e.outcome == "success"


def test_audit_filters() -> None:
    svc = _audit()
    svc.record("auth.login_failed", actor_username="bob", outcome="failure")
    svc.record("company.create", actor=ACTOR, entity_type="Company")
    assert len(svc.list_events(outcome="failure")) == 1
    assert len(svc.list_events(action="company.create")) == 1
    assert len(svc.list_events(actor="ali")) == 1  # substring match
    assert svc.count_events() == 2


def test_audit_never_stores_secrets() -> None:
    svc = _audit()
    svc.record(
        "user.create",
        actor=ACTOR,
        changes={"username": "x", "password": "hunter2", "api_key": "sk-live-abc"},
    )
    summary = svc.list_events()[0].summary
    assert "hunter2" not in summary
    assert "sk-live-abc" not in summary
    assert "[redacted]" in summary
    assert "username=x" in summary


def test_redact_and_summarize_helpers() -> None:
    red = redact({"token": "abc", "name": "keep"})
    assert red["token"] == "[redacted]" and red["name"] == "keep"
    assert summarize(None) == ""
    long = summarize({"note": "z" * 200})
    assert long.endswith("...")


def test_authorization_denial_is_auditable() -> None:
    svc = _audit()
    svc.record(
        "authz.denied",
        actor=ACTOR,
        entity_type="Company",
        entity_id="c9",
        outcome="denied",
        reason="not owner",
    )
    e = svc.list_events(outcome="denied")[0]
    assert e.outcome == "denied" and e.reason == "not owner"


def test_analytics_track_and_counts() -> None:
    svc = _analytics()
    svc.track(LOGIN_SUCCESS, user_id="u1")
    svc.track(COMPANY_CREATED, user_id="u1")
    svc.track(COMPANY_CREATED, user_id="u2")
    counts = svc.counts()
    assert counts[COMPANY_CREATED] == 2
    assert counts[LOGIN_SUCCESS] == 1
    assert len(svc.list_events(name=COMPANY_CREATED)) == 2


def test_audit_and_analytics_are_separate_stores() -> None:
    audit_repo = InMemoryAuditRepository()
    product_repo = InMemoryProductEventRepository()
    AuditService(audit_repo).record("company.create", actor=ACTOR)
    AnalyticsService(product_repo).track(COMPANY_CREATED, user_id="u1")
    # Each store holds only its own kind of event.
    assert audit_repo.count_events() == 1
    assert product_repo.count_by_name() == {COMPANY_CREATED: 1}
    assert audit_repo.list_events()[0].action == "company.create"
    assert product_repo.list_events()[0].name == COMPANY_CREATED
