from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./recruitment.db"

    # Lever is the ONLY external provider this service owns (Architecture
    # Completion Plan §3). GET-only — CLAUDE.md §60 LIVE LEVER SAFETY
    # CONTRACT. Mock by default; a real key only takes effect outside
    # INTEGRATIONS_MODE=mock.
    integrations_mode: str = "mock"
    lever_api_key: str = ""
    lever_base_url: str = "https://api.lever.co/v1"
    lever_webhook_signing_secret: str = ""

    api_cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )

    # Must match platform-api's JWT_DEV_SECRET (claims decoded locally, same
    # as every other business service) and the shared INTERNAL_SERVICE_SECRET.
    jwt_dev_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"

    platform_api_url: str = "http://localhost:8000"
    internal_service_secret: str = "dev-only-internal-secret-change-me"

    # Bounded per-run opportunity pull (CLAUDE.md §60 "minimum reasonable
    # requests"); a tenant can have very large candidate counts.
    opportunity_sync_limit: int = 200

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
