import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import op

config = context.config
url = os.environ.get("DATABASE_URL", "postgresql://noa:noa@localhost:5433/noa")
config.set_main_option("sqlalchemy.url", url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = None


def run_migrations_offline() -> None:
    url = os.environ.get("DATABASE_URL", "postgresql://noa:noa@localhost:5433/noa")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    connectable = engine_from_config(
        {"sqlalchemy.url": url},
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
