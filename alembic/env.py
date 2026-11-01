"""Alembic environment – uses synchronous psycopg2 URL for migrations."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Load app models so Alembic can autogenerate migrations
from app.models.base import Base  # noqa: F401
import app.models  # noqa: F401 – registers all mappers

config = context.config

# Override sqlalchemy.url from the environment variable so we never store
# credentials in alembic.ini.
sync_url = os.environ.get(
    "SYNC_DATABASE_URL",
    "postgresql+psycopg2://queueguard:queueguard@localhost:5432/queueguard",
)
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
