-- Runs once, on first cluster initialization (docker-entrypoint-initdb.d).
-- talvrin (the POSTGRES_USER) is a superuser and therefore bypasses RLS no
-- matter what FORCE ROW LEVEL SECURITY says — the app and tests must run as
-- a genuinely unprivileged role for RLS policies to mean anything.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'talvrin_app') THEN
        CREATE ROLE talvrin_app LOGIN PASSWORD 'talvrin_app' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE talvrin TO talvrin_app;
