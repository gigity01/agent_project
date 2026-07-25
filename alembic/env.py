"""Alembic 运行环境：将应用 ORM 元数据与数据库 URL 提供给迁移上下文。"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.app_config.settings import SQLALCHEMY_DATABASE_URL
from app.db.session import Base

import app.models

# Alembic 配置对象来自 alembic.ini；运行时 URL 由应用统一配置覆盖，避免迁移
# 与服务连接到不同数据库。
config = context.config
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)

# 仅在存在 ini 文件时初始化 Alembic 自身日志。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 自动生成迁移时以应用 Base.metadata 为唯一模型来源。
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """以离线模式生成 SQL，不创建数据库连接。"""
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
    """以在线模式建立临时连接并在受控事务中执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
