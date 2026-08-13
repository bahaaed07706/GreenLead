"""Record-level authorization policy — the single source of truth.

Every service consults this module; no route or template re-implements rules.

Policy (documented and enforced):

* **Employee** — may view/modify only records whose ``owner_id`` is their own
  user id. Unassigned records (empty ``owner_id``) are NOT visible to
  employees: this fails closed, so records that predate ownership stay hidden
  until a manager assigns them.
* **Manager** — may view every record and may (re)assign ownership.
* **Admin** — may view every record and may (re)assign ownership.

Known limitation: there is no Team entity yet, so "team" means *all* users.
When teams are introduced, only ``_sees_all`` and ``visible_owner_ids`` need to
change — call sites stay untouched.
"""

from collections.abc import Iterable, Sequence
from typing import Protocol, TypeVar

from greenlead.models.schemas import User

ROLE_EMPLOYEE = "employee"
ROLE_MANAGER = "manager"
ROLE_ADMIN = "admin"

ELEVATED_ROLES = frozenset({ROLE_MANAGER, ROLE_ADMIN})


class AccessDenied(Exception):
    """Raised when the actor may not access or modify a record."""


class Owned(Protocol):
    """Anything carrying an ``owner_id`` (Company, Contact, FollowUp, Meeting)."""

    owner_id: str


T = TypeVar("T", bound=Owned)


def _sees_all(user: User) -> bool:
    """True when the role grants organisation-wide visibility."""
    return user.role in ELEVATED_ROLES


def can_view(user: User, owner_id: str) -> bool:
    """May ``user`` view a record owned by ``owner_id``?"""
    if _sees_all(user):
        return True
    return bool(owner_id) and owner_id == user.id


def can_edit(user: User, owner_id: str) -> bool:
    """May ``user`` modify a record owned by ``owner_id``?

    Same rule as viewing: employees own what they can change.
    """
    return can_view(user, owner_id)


def can_reassign(user: User) -> bool:
    """Only managers and admins may change record ownership."""
    return user.role in ELEVATED_ROLES


def can_manage_users(user: User) -> bool:
    """Only admins manage user accounts."""
    return user.role == ROLE_ADMIN


def can_view_related(user: User, owner_id: str, parent_owner_id: str) -> bool:
    """Access to a child record (Contact/Follow-up/Meeting).

    Granted when the actor owns the record itself *or* owns the parent Company,
    so an employee working an account sees everything hanging off it.
    """
    return can_view(user, owner_id) or can_view(user, parent_owner_id)


def require_view_related(user: User, owner_id: str, parent_owner_id: str) -> None:
    if not can_view_related(user, owner_id, parent_owner_id):
        raise AccessDenied("You do not have access to this record.")


def filter_visible_related(user: User, pairs: Iterable[tuple[T, str]]) -> list[T]:
    """Filter ``(record, parent_owner_id)`` pairs down to the visible records."""
    if _sees_all(user):
        return [r for r, _ in pairs]
    return [r for r, parent in pairs if can_view_related(user, r.owner_id, parent)]


def require_view(user: User, owner_id: str) -> None:
    """Raise :class:`AccessDenied` unless the actor may view the record."""
    if not can_view(user, owner_id):
        raise AccessDenied("You do not have access to this record.")


def require_edit(user: User, owner_id: str) -> None:
    """Raise :class:`AccessDenied` unless the actor may modify the record."""
    if not can_edit(user, owner_id):
        raise AccessDenied("You do not have access to this record.")


def require_reassign(user: User) -> None:
    if not can_reassign(user):
        raise AccessDenied("Only a manager or admin may reassign records.")


def filter_visible(user: User, records: Iterable[T]) -> list[T]:
    """Return only the records the actor is authorised to see."""
    if _sees_all(user):
        return list(records)
    return [r for r in records if r.owner_id and r.owner_id == user.id]


def visible_owner_ids(user: User) -> Sequence[str] | None:
    """Owner ids the actor may see, or ``None`` meaning "no restriction".

    Lets repositories push filtering into SQL later without changing callers.
    """
    if _sees_all(user):
        return None
    return [user.id]
