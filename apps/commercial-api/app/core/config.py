from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./commercial.db"

    # Commercial/CRM domain — architectural seam, deferred (Architecture
    # Completion Plan §3/Wave F). No live HubSpot client is implemented;
    # mock-only until read-only access is requested at ~55-65% maturity
    # (CLAUDE.md §59) and this domain owns Commercial/CRM facts, never
    # canonical Client identity (that stays platform-owned — §6.1).
    integrations_mode: str = "mock"
    hubspot_access_token: str = ""
    hubspot_base_url: str = "https://api.hubapi.com"

    api_cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )

    jwt_dev_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"

    platform_api_url: str = "http://localhost:8000"
    internal_service_secret: str = "dev-only-internal-secret-change-me"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
