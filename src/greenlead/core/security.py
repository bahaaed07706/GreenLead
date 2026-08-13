from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address

from greenlead.core.config import get_settings

if TYPE_CHECKING:
    from greenlead.models.schemas import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
limiter = Limiter(key_func=get_remote_address)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_session_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key)


def create_session_token(username: str) -> str:
    serializer = get_session_serializer()
    return serializer.dumps({"username": username})


def verify_session_token(token: str, max_age: int = 86400 * 7) -> str | None:
    # 7 days max age by default
    serializer = get_session_serializer()
    try:
        data: dict = serializer.loads(token, max_age=max_age)  # type: ignore
        return data.get("username")
    except (BadSignature, SignatureExpired):
        return None


def _resolve_active_user(request: Request) -> "User":
    """Resolve the session cookie to an active User, or raise. Returns a User.

    Bootstraps the initial admin (idempotent) so a fresh install / test always
    has the configured admin available. Lazy imports avoid a circular import
    (services.users depends on core.security).
    """
    from greenlead.repositories import get_user_repository
    from greenlead.services.users import UserService

    token = request.cookies.get("session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND, headers={"Location": "/login"}
        )
    username = verify_session_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_302_FOUND, headers={"Location": "/login"}
        )

    service = UserService(get_user_repository())
    service.ensure_bootstrap_admin(get_settings())
    user = service.get_by_username(username)
    if user is None or not user.is_active:
        # Account removed/deactivated -> session is no longer valid.
        raise HTTPException(
            status_code=status.HTTP_302_FOUND, headers={"Location": "/login"}
        )
    return user


def get_current_user(request: Request) -> str:
    """FastAPI dependency: the authenticated, active user's username."""
    return _resolve_active_user(request).username


def get_current_user_obj(request: Request) -> "User":
    """FastAPI dependency: the authenticated, active :class:`User` object.

    Routes that enforce record-level authorization use this and pass the user
    into the service ``*_for`` methods.
    """
    return _resolve_active_user(request)


def require_role(minimum: str):  # type: ignore[no-untyped-def]
    """Return a dependency that allows only users at/above ``minimum`` role.

    Ranking: employee < manager < admin. Raises 403 when insufficient.
    """
    from greenlead.services.users import ROLE_RANK

    required = ROLE_RANK.get(minimum, 99)

    def _dep(request: Request) -> str:
        user = _resolve_active_user(request)
        if ROLE_RANK.get(user.role, 0) < required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user.username

    return _dep
