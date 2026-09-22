-- Runs once, on first cluster initialization (docker-entrypoint-initdb.d).
-- A genuinely separate database for integration tests, so
-- tests/integration/conftest.py's per-test TRUNCATE never touches the same
-- rows a live dev server (or a browser session testing against it) is
-- using. See backend/README.md's "Testing" section for the incident this
-- fixes: running the integration suite while also testing through the
-- browser used to silently wipe the signed-in account/conversation and
-- all seeded governance/reference data mid-session.
--
-- CREATE DATABASE cannot run inside a transaction block, hence \gexec
-- rather than a DO $$ ... $$ guard (which works fine for CREATE ROLE).
SELECT 'CREATE DATABASE talvrin_test OWNER talvrin'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'talvrin_test')
\gexec

GRANT CONNECT ON DATABASE talvrin_test TO talvrin_app;
