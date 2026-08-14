from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./birthday.db"

    integrations_mode: str = "mock"
    # Independent from integrations_mode (Phase-Next §7/§8): lets BambooHR
    # stay live while email sending stays mocked during the dry-run phase,
    # rather than one shared switch forcing both integrations to move
    # together. Defaults mock — real supplier email requires an explicit
    # opt-in, never an accidental side effect of enabling live BambooHR.
    email_sending_mode: str = "mock"

    api_cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )

    # Must match platform-api's JWT_DEV_SECRET — birthday-api verifies
    # tokens locally from claims, exactly like talent-api, proving the
    # module-framework authorization seam works before any real business
    # logic exists (CR §9).
    jwt_dev_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"

    platform_api_url: str = "http://localhost:8000"
    # Must match platform-api's INTERNAL_SERVICE_SECRET.
    internal_service_secret: str = "dev-only-internal-secret-change-me"

    # Microsoft Graph email adapter (plan §9) — client-credentials flow.
    # Unset until the user completes Graph app registration; GraphEmailClient
    # raises GraphNotConfiguredError until all four are set.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_sender_mailbox: str = ""

    # BambooHR employee-directory adapter — REST API key auth (basic auth,
    # username=API key, password="x", per BambooHR's documented convention).
    # Unset until real BambooHR credentials are supplied; BambooHRHttpClient
    # raises BambooHRNotConfiguredError until both are set. Never fabricated
    # (CLAUDE.md §58) — mock remains the default via INTEGRATIONS_MODE=mock.
    bamboohr_api_key: str = ""
    bamboohr_subdomain: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
