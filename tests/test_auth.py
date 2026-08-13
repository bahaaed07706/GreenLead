from fastapi.testclient import TestClient

from greenlead.application import create_app

app = create_app()
client = TestClient(app)


def test_login_page_renders() -> None:
    response = client.get("/login")
    assert response.status_code == 200
    assert "تسجيل الدخول" in response.text


def test_unauthenticated_dashboard_redirects() -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers.get("location", "")


def test_login_success_and_failure() -> None:
    """Authenticate against a real seeded user (bcrypt-hashed by the service)."""
    from greenlead.models.schemas import UserCreate
    from greenlead.repositories import get_user_repository, reset_repository
    from greenlead.services.users import UserService

    reset_repository()
    UserService(get_user_repository()).create_user(
        UserCreate(username="bdr1", password="correct-horse", role="employee")
    )

    # Successful login
    response = client.post(
        "/login",
        data={"username": "bdr1", "password": "correct-horse"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers.get("location") == "/"
    assert "session=" in response.headers.get("set-cookie", "")

    # Failed login (wrong password)
    response_fail = client.post(
        "/login",
        data={"username": "bdr1", "password": "wrong"},
        follow_redirects=False,
    )
    assert response_fail.status_code == 401
    assert "بيانات الاعتماد غير صالحة" in response_fail.text
    reset_repository()


def test_logout() -> None:
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/login"
    assert "session=" in response.headers.get("set-cookie", "")
    assert "Max-Age=0" in response.headers.get(
        "set-cookie", ""
    ) or "expires=" in response.headers.get("set-cookie", "")


def test_language_switch() -> None:
    response = client.get("/set-language?lang=en", follow_redirects=False)
    assert response.status_code == 302
    assert "lang=en" in response.headers.get("set-cookie", "")

    # Check if English text is rendered when cookie is set
    response_en = client.get("/login", cookies={"lang": "en"})
    assert response_en.status_code == 200
    assert "Sign In" in response_en.text
    assert 'dir="ltr"' in response_en.text
