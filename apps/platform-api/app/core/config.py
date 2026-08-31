from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite:///./platform.db"

    # "dev"  -> Dev Identity Mode persona switcher (local + first shared DEV)
    # "entra" -> Microsoft Entra ID OIDC (Authorization Code + PKCE)
    auth_mode: str = "dev"
    dev_identity_mode: bool = True  # legacy flag, still honoured alongside auth_mode
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""
    entra_redirect_uri: str = ""
    # Public origin of this environment (e.g. https://dijione-dev.example.com).
    # Used to build the Entra front-channel logout redirect.
    public_base_url: str = ""

    # Next.js falls back to :3001, :3002, ... when :3000 is already in use
    # by another local process, so local dev allows a small range rather
    # than a single hardcoded origin. Production sets this explicitly.
    api_cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )
    jwt_dev_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 12

    # Dev-only shared secret trusted service-to-service calls present on the
    # `X-Internal-Token` header (talent-api/birthday-api/spark-api writing
    # audit events or notifications; admin-api reading service summaries).
    # Not a production trust model — see docs/platform/service-contracts.md
    # "Service-to-service trust boundaries".
    internal_service_secret: str = "dev-only-internal-secret-change-me"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def dev_auth_enabled(self) -> bool:
        """Dev Identity Mode is active only when explicitly selected AND not
        overridden to Entra. Both switches must agree, so an environment that
        sets AUTH_MODE=entra can never accidentally leave the passwordless
        persona switcher exposed."""
        return self.auth_mode == "dev" and self.dev_identity_mode

    @property
    def entra_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}"

    @property
    def entra_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.entra_tenant_id}/v2.0"

    @property
    def entra_jwks_uri(self) -> str:
        return f"{self.entra_authority}/discovery/v2.0/keys"


@lru_cache
def get_settings() -> Settings:
    return Settings()
