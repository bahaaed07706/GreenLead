"""User account business service: bootstrap, authentication, and management.

Password hashing/verification lives in core.security; hashes never leave the
repository except for the single verify step here.
"""

import logging
from datetime import UTC, datetime

from greenlead.core.config import Settings
from greenlead.core.security import get_password_hash as hash_password
from greenlead.core.security import verify_password
from greenlead.models.schemas import User, UserCreate
from greenlead.repositories.base import UserRepository

logger = logging.getLogger(__name__)

VALID_ROLES = frozenset({"employee", "manager", "admin"})
# Role -> the roles it is allowed to act as (for require_role hierarchy).
ROLE_RANK = {"employee": 1, "manager": 2, "admin": 3}


class UserService:
    def __init__(self, user_repo: UserRepository) -> None:
        self._repo = user_repo

    def ensure_bootstrap_admin(self, settings: Settings) -> None:
        """Seed the configured admin from env if absent (idempotent).

        Keyed on the admin username (not table emptiness) so seeding other users
        first can never lock out the admin account.
        """
        if not settings.admin_username:
            return
        if self._repo.get_user_by_username(settings.admin_username) is not None:
            return
        # settings.admin_password_hash is already a bcrypt hash; store as-is.
        self._repo.create_user(
            UserCreate(
                username=settings.admin_username,
                password="__bootstrap__",  # not used; real hash passed below
                name="Administrator",
                role="admin",
                created_by="system",
            ),
            password_hash=settings.admin_password_hash or "",
        )
        logger.info("Bootstrapped initial admin user '%s'", settings.admin_username)

    def list_users(self) -> list[User]:
        return self._repo.list_users()

    def get_by_username(self, username: str) -> User | None:
        return self._repo.get_user_by_username(username)

    def create_user(self, data: UserCreate) -> User:
        if data.role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {data.role}")
        if not data.username.strip():
            raise ValueError("Username is required.")
        if self._repo.get_user_by_username(data.username) is not None:
            raise ValueError(f"Username already exists: {data.username}")
        user = self._repo.create_user(data, hash_password(data.password))
        logger.info("User created: %s (role=%s)", user.username, user.role)
        return user

    def authenticate(self, username: str, password: str) -> User | None:
        """Return the user on valid credentials AND active account, else None."""
        user = self._repo.get_user_by_username(username)
        if user is None or not user.is_active:
            return None
        stored = self._repo.get_password_hash(username)
        if not stored or not verify_password(password, stored):
            return None
        self._repo.update_user(user.id, {"last_login": datetime.now(UTC).isoformat()})
        return user

    def set_active(self, user_id: str, active: bool) -> User:
        return self._repo.update_user(user_id, {"is_active": active})

    def set_role(self, user_id: str, role: str) -> User:
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")
        return self._repo.update_user(user_id, {"role": role})
