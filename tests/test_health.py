from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.core.config import get_settings

app = create_app()
client = TestClient(app)


def test_app_creation() -> None:
    """Test that the application factory works."""
    assert app.title == "GreenLead"


def test_health_check_returns_200() -> None:
    """Test GET /health returns HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_schema() -> None:
    """Test the structure of the health response."""
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert "environment" in data
    assert data["status"] == "ok"
    assert data["service"] == "greenlead"


def test_environment_value_derived_safely() -> None:
    """Test that the environment comes from settings safely."""
    settings = get_settings()
    response = client.get("/health")
    data = response.json()
    assert data["environment"] == settings.app_env


def test_no_secrets_in_health_response() -> None:
    """Ensure no secrets are leaked in the health endpoint."""
    response = client.get("/health")
    data = response.json()
    settings = get_settings()

    # Simple check that the secret_key is not in any values
    for value in data.values():
        assert value != settings.secret_key
