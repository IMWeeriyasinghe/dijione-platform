from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./talent.db"

    integrations_mode: str = "mock"
    lever_api_key: str = ""
    lever_base_url: str = "https://api.lever.co/v1"
    # Optional. When unset, inbound Lever webhooks are accepted without
    # signature verification (logged as a warning) — this dev environment
    # has no production webhook configured yet (CLAUDE.md §60/§63). When
    # set, an invalid/missing signature is rejected with 401.
    lever_webhook_signing_secret: str = ""
    hubspot_access_token: str = ""
    hubspot_base_url: str = "https://api.hubapi.com"

    azure_storage_connection_string: str = ""

    api_cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )

    # Must match platform-api's JWT_DEV_SECRET — talent-api verifies tokens
    # locally from claims, it never calls Platform Core to authenticate a
    # request (see packages/auth-client-py).
    jwt_dev_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"

    platform_api_url: str = "http://localhost:8000"
    # Must match platform-api's INTERNAL_SERVICE_SECRET.
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
