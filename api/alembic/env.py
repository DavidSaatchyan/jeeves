import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import Base and all models so they're registered
from app.db import Base
from app.models import *  # noqa: F401,F403

# Get the database URL from our config
from app.config import get_settings

settings = get_settings()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = context.config.get_main_option("sqlalchemy.url")
    if not url or url == "driver://user:pass@localhost/dbname":
        url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = context.config.get_section(context.config.config_ini_section, {})
    db_url = configuration.get("sqlalchemy.url", settings.database_url)
    if db_url == "driver://user:pass@localhost/dbname":
        db_url = settings.database_url
    configuration["sqlalchemy.url"] = db_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
