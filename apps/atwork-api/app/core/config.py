from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./atwork.db"
    business_time_zone: str = "Asia/Colombo"

    api_cors_origins: str = "http://localhost:3000,http://localhost:3005,http://127.0.0.1:3000,http://127.0.0.1:3005"

    # Must match platform-api's PLATFORM_JWT_SECRET: signed claims are
    # verified locally, with no call back to Platform Core. The insecure
    # defaults are rejected outside development by assert_trust_anchors_safe.
    platform_jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    internal_service_secret: str = "dev-only-internal-secret-change-me"

    # The foundation has no external integrations.
    integrations_mode: str = "mock"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
