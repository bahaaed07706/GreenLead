from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GreenLead"
    app_env: str = "development"

    # Branding / organization.
    # These carry no business logic — they are the labels and defaults shown in
    # the UI, so the platform can be adapted to any company, role or industry
    # without touching code. See docs/CUSTOMIZATION.md.
    org_name: str = "Your Company"
    org_industry: str = "Technology"
    app_description: str = "Business-development & sales-intelligence platform"
    app_debug: bool = False
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    secret_key: str = "replace-with-secure-secret"

    # Authentication
    admin_username: str = "admin"
    admin_password_hash: str = ""

    # Persistence
    # When set (e.g. sqlite:///./greenlead.db or postgresql+psycopg://...),
    # the SQL repository backend is used and data survives restarts.
    # When empty, the in-memory backend is used (data lost on restart).
    database_url: str | None = None

    # Future Phase Placeholders
    ai_provider: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    tavily_api_key: str | None = None
    google_sheet_id: str | None = None
    google_service_account_file: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


def get_settings() -> Settings:
    return Settings()
