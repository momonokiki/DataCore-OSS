import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 1. アプリケーションの設定とBase/全モデルをインポート
from app.core.config import settings
from app.infrastructure.db.base import Base

# ★ マイグレーション対象に含めるため、作成したすべてのモデルを明示的に読み込みます
from app.infrastructure.db.models import users, l2_tools, l3_tools, job_queue, auth  # noqa
from app.layers.l1_raw import models as l1_models  # noqa
from app.layers.l2_extracted import models as l2_models  # noqa

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 2. alembic.ini の sqlalchemy.url を .env の DATABASE_URL で上書き（ハードコーディング回避）
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def include_object(object, name, type_, reflected, compare_to):
    """
    Alembicの管理対象を制限するフック
    テーブル名が 'addon_' で始まる場合は、Alembicの自動生成対象から完全に除外します。
    """
    if type_ == "table":
        # 1. L3アドオンテーブルの除外
        if name.startswith("addon_"):
            return False
        # 2. Celery (Kombu) 内部テーブルの除外
        if name.startswith("kombu_"):
            return False
            
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """同期コンテキスト内でマイグレーションを実行"""
    context.configure(connection=connection, target_metadata=target_metadata,include_object=include_object)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """非同期エンジンを使用したオンラインマイグレーション実行"""
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

