import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context
from sqlalchemy import create_engine

from app.db.models import Clients, SyncState
from app.db.models import BonusLog

# 1) Добавляем корень проекта в PYTHONPATH, чтобы работал import app.config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 2) Импортируем настройки
from app.config import settings
from sqlmodel import SQLModel

# 3) Объект Alembic Config
config = context.config

# 4) Подменяем URL подключения на тот, что в .env / app/config.py
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 5) Настройка логирования из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 6) MetaData ваших моделей - для autogenerate
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Запуск без реального подключения (offline mode)."""
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
    """Запуск с реальным подключением (online mode)."""
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")

    # Создаём синхронный движок
    connectable = create_engine(
        sync_url,
        poolclass=pool.NullPool,
        echo=False
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


# 7) Ветка offline/online
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
