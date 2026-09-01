from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./talent.db"

    # Lever is owned by the Recruitment Source domain (recruitment-api) —
    # talent-api holds NO Lever key. It consumes postings/candidacies over
    # the recruitment-api HTTP contract. HubSpot moved to the Commercial/CRM
    # domain skeleton (commercial-api) — talent-api holds no HubSpot key
    # either (Architecture Completion Plan Wave F).
    integrations_mode: str = "mock"
    recruitment_api_url: str = "http://localhost:8005"

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

    # DijiTalentFlow magic-link external client sessions — a DELIBERATELY
    # SEPARATE signing secret + issuer from jwt_dev_secret/
    # "dijione-dev-identity" (approved security amendment). An
    # internally-signed staff token must never verify against this secret,
    # and an externally-signed session must never verify against
    # jwt_dev_secret — see get_talent_external_scope in app/api/deps.py.
    # Local-dev-only default; production provisioning is a future,
    # separate cloud task, not something this value needs to anticipate.
    external_session_jwt_secret: str = "dev-only-external-session-secret-change-me"
    external_session_jwt_issuer: str = "dijitalent-external"
    # Short-lived by design: an external session cannot be refreshed — the
    # SPA silently re-redeems the stored raw token for a fresh session
    # while the grant is still valid (revoke/expiry then stops it within
    # this window). Kept inside the plan's 30–60 min band.
    external_session_jwt_ttl_minutes: int = 45

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
