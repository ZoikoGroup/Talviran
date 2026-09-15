from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    # Runtime app connection: the unprivileged `talvrin_app` role (created by
    # infra/init-db/01-roles.sql) — this is the role RLS policies actually
    # apply to. Never point this at the superuser.
    database_url: str = "postgresql+asyncpg://talvrin_app:talvrin_app@localhost:5433/talvrin"

    # Migrations only (Alembic reads this, not database_url): the superuser
    # role, since DDL (CREATE TABLE/SCHEMA/POLICY) needs privileges the app
    # role deliberately doesn't have.
    admin_database_url: str = "postgresql+asyncpg://talvrin:talvrin@localhost:5433/talvrin"

    redis_url: str = "redis://localhost:6380/0"
    dmo_base_url: str = "https://www.dmo.gov.uk"
    secret_key: str = "dev-only-change-me"
    cors_allow_origins: list[str] = ["http://localhost:5173"]

    # Wraps the per-account data keys that encrypt research content
    # (SEC-001 §15.1). Base64 of 32 bytes. The default is a fixed development
    # value and is useless as a secret — `CookiePolicy.for_environment` style
    # fail-closed behaviour lives in research.keys.build_key_wrapper, which
    # refuses to start outside development unless this is overridden or a KMS
    # key is configured instead.
    content_master_key: str = "ZGV2LW9ubHktbWFzdGVyLWtleS0zMi1ieXRlcyEhISE="

    # Set in production to wrap DEKs with Cloud KMS rather than a local key:
    # "projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>".
    kms_key_name: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
