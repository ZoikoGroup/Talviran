import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.core.db import Base

# Importing each module's models.py registers its tables on Base.metadata so
# autogenerate sees them. Add a line here as each module gains a models.py.
from app.modules.audit import models as audit_models  # noqa: F401
from app.modules.evidence import models as evidence_models  # noqa: F401
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.market import models as market_models  # noqa: F401
from app.modules.policy import models as policy_models  # noqa: F401
from app.modules.reference import models as reference_models  # noqa: F401
from app.modules.rights import models as rights_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations run as the superuser (admin_database_url), never the restricted
# talvrin_app runtime role — DDL needs privileges the app role deliberately
# lacks. Comes from Settings (.env) rather than alembic.ini, so there is one
# source of truth for connection strings across the app and migrations.
config.set_main_option("sqlalchemy.url", get_settings().admin_database_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # include_schemas=True: our tables live in identity/reference/market/...,
    # never in `public` — without this, autogenerate can't see them.
    context.configure(
        connection=connection, target_metadata=target_metadata, include_schemas=True
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
