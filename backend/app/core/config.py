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

    # A genuinely separate database for tests/integration (infra/init-db/
    # 02-test-database.sql creates it) - conftest.py's db_session/
    # _truncate_test_tables point here, never at database_url/
    # admin_database_url. Before this existed, running the integration
    # suite while also testing through the browser silently wiped the
    # signed-in account/conversation and all seeded governance/reference
    # data mid-session - a real incident, not a hypothetical one.
    test_database_url: str = (
        "postgresql+asyncpg://talvrin_app:talvrin_app@localhost:5433/talvrin_test"
    )
    test_admin_database_url: str = "postgresql+asyncpg://talvrin:talvrin@localhost:5433/talvrin_test"

    redis_url: str = "redis://localhost:6380/0"
    dmo_base_url: str = "https://www.dmo.gov.uk"

    # Local-filesystem backend for market.SourceArtifact.storage_ref
    # (ENG-ARCH-003 names S3-compatible object storage as the eventual
    # target - not wired up yet, same gap SourceArtifact's own docstring
    # flags). Content-addressed by sha256, so this default is safe to
    # share across dev/test runs on one machine.
    artifact_storage_root: str = "var/artifacts"
    secret_key: str = "dev-only-change-me"
    cors_allow_origins: list[str] = ["http://localhost:5173"]

    # Where a Supabase password-reset email should send the user back to —
    # the frontend's own origin, not one of (possibly several)
    # cors_allow_origins, which answers a different question (who may call
    # this API from a browser) and shouldn't be overloaded to answer this one.
    frontend_url: str = "http://localhost:5173"

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

    # Supabase Auth (GoTrue) is the credential and session engine — see
    # identity/supabase_auth.py. Required, not defaulted: an app that started
    # with no way to reach its own auth provider should fail at boot, not on
    # the first user's sign-in attempt.
    supabase_url: str
    #: The public anon key. Safe to ship to a browser by Supabase's own
    #: design; used here from the backend only, which is a strictly smaller
    #: exposure than that.
    supabase_anon_key: str
    #: Not used by anything yet — reserved for a future admin operation
    #: (e.g. force-deleting a Supabase user on account deletion) that would
    #: need it. Optional so its absence doesn't block everything else.
    supabase_service_role_key: str | None = None

    #: Twelve Data equities connector (free tier, ~8 requests/minute).
    #: Optional, not required at boot: only the equity connector itself
    #: needs it, and only when it actually runs.
    twelve_data_api_key: str | None = None

    #: Gemini embeddings (P4 EVID-001 E3 semantic retrieval) and generation
    #: (P4b ai_gateway - talvrin-pro's registered provider, though the
    #: "pro" model line has zero free-tier quota on this key as of
    #: 2026-09-22; see ai_gateway/providers/gemini_client.py). Optional,
    #: not required at boot: only the pipelines that use it need it.
    gemini_api_key: str | None = None

    #: Groq (P4b ai_gateway - talvrin-go's registered provider, PRODUCTION
    #: since live-verified 2026-09-22; see ai_gateway/providers/
    #: groq_client.py). Optional, not required at boot: only the ai_gateway
    #: pipelines that use it need it.
    groq_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
