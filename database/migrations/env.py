"""Alembic environment for the async API database."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import inspect, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from database.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        # Alembic's default version table uses VARCHAR(32), but this project's
        # descriptive revision IDs exceed that limit. Create or widen its
        # bookkeeping column before Alembic records any revision.
        # Commit this bootstrap before configuring Alembic. Otherwise SQLAlchemy
        # treats the implicit transaction as externally managed and migration
        # DDL can be rolled back when the connection closes.
        with connection.begin():
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(128) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                ")"
            )
            version_column = next(
                column
                for column in inspect(connection).get_columns("alembic_version")
                if column["name"] == "version_num"
            )
            length = getattr(version_column["type"], "length", None)
            if length is not None and length < 128:
                connection.exec_driver_sql(
                    "ALTER TABLE alembic_version "
                    "ALTER COLUMN version_num TYPE VARCHAR(128)"
                )
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
