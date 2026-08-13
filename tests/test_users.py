"""Tests for Users, authentication, and RBAC enforcement."""

import pytest
from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.core.security import create_session_token
from greenlead.models.schemas import UserCreate
from greenlead.repositories import get_user_repository, reset_repository
from greenlead.services.users import UserService


def _service() -> UserService:
    return UserService(get_user_repository())


def _client() -> TestClient:
    return TestClient(create_app(), follow_redirects=False)


def _session(username: str) -> dict[str, str]:
    return {"session": create_session_token(username)}


# ── Service ───────────────────────────────────────────────────────────────────


def test_create_and_authenticate() -> None:
    reset_repository()
    svc = _service()
    user = svc.create_user(
        UserCreate(username="alice", password="s3cret-pass", role="manager")
    )
    assert user.role == "manager" and user.is_active
    assert svc.authenticate("alice", "s3cret-pass") is not None
    assert svc.authenticate("alice", "wrong") is None
    assert svc.authenticate("ghost", "x") is None


def test_authenticate_inactive_denied() -> None:
    reset_repository()
    svc = _service()
    u = svc.create_user(UserCreate(username="bob", password="pw12345"))
    svc.set_active(u.id, False)
    assert svc.authenticate("bob", "pw12345") is None


def test_duplicate_username_and_bad_role_rejected() -> None:
    reset_repository()
    svc = _service()
    svc.create_user(UserCreate(username="dup", password="pw12345"))
    with pytest.raises(ValueError):
        svc.create_user(UserCreate(username="dup", password="pw12345"))
    with pytest.raises(ValueError):
        svc.create_user(UserCreate(username="x", password="pw", role="superuser"))


def test_password_hash_not_plaintext() -> None:
    reset_repository()
    svc = _service()
    svc.create_user(UserCreate(username="carol", password="plaintext-pw"))
    stored = get_user_repository().get_password_hash("carol")
    assert stored and stored != "plaintext-pw" and stored.startswith("$2")


def test_bootstrap_admin_idempotent() -> None:
    reset_repository()
    from greenlead.core.config import Settings

    svc = _service()
    settings = Settings(admin_username="admin", admin_password_hash="$2b$12$abc")
    svc.ensure_bootstrap_admin(settings)
    svc.ensure_bootstrap_admin(settings)  # second call is a no-op
    admins = [u for u in svc.list_users() if u.username == "admin"]
    assert len(admins) == 1 and admins[0].role == "admin"


# ── RBAC route enforcement ────────────────────────────────────────────────────


def test_admin_route_requires_admin_role() -> None:
    reset_repository()
    _service().create_user(
        UserCreate(username="emp", password="pw12345", role="employee")
    )
    client = _client()

    # Unauthenticated -> redirect to login.
    assert client.get("/admin/users").status_code == 302

    # Employee -> forbidden.
    client.cookies.update(_session("emp"))
    assert client.get("/admin/users").status_code == 403

    # Admin (bootstrapped on first auth) -> allowed.
    admin_client = _client()
    admin_client.cookies.update(_session("admin"))
    assert admin_client.get("/admin/users").status_code == 200


def test_employee_cannot_deactivate_users_idor() -> None:
    reset_repository()
    svc = _service()
    svc.create_user(UserCreate(username="emp2", password="pw12345", role="employee"))
    # Force admin to exist so we have a target id.
    admin_client = _client()
    admin_client.cookies.update(_session("admin"))
    admin_client.get("/")  # triggers bootstrap
    admin = svc.get_by_username("admin")
    assert admin is not None

    emp_client = _client()
    emp_client.cookies.update(_session("emp2"))
    resp = emp_client.post(f"/admin/users/{admin.id}/deactivate")
    assert resp.status_code == 403
    assert svc.get_by_username("admin").is_active is True  # unchanged


def test_admin_creates_user_via_route() -> None:
    reset_repository()
    client = _client()
    client.cookies.update(_session("admin"))
    client.get("/")  # bootstrap admin
    resp = client.post(
        "/admin/users/new",
        data={"username": "newbdr", "password": "pw123456", "role": "employee"},
    )
    assert resp.status_code == 303
    assert _service().get_by_username("newbdr") is not None


def test_deactivated_user_session_invalidated() -> None:
    reset_repository()
    svc = _service()
    u = svc.create_user(
        UserCreate(username="temp", password="pw12345", role="employee")
    )
    client = _client()
    client.cookies.update(_session("temp"))
    # Active -> dashboard loads.
    assert client.get("/").status_code == 200
    # Deactivate -> same session is now rejected (redirect to login).
    svc.set_active(u.id, False)
    assert client.get("/").status_code == 302
    reset_repository()
