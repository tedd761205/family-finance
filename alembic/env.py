import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.database import Base
from app import models  # noqa: F401


# Alembic 設定
config = context.config

# 載入 logging 設定
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# SQLAlchemy 所有模型的 Metadata
target_metadata = Base.metadata


def get_database_url():
    """從環境變數取得資料庫連線資訊"""

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "環境變數 DATABASE_URL 尚未設定"
        )

    # 統一使用 psycopg 3
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1
        )

    return database_url


def run_migrations_offline():
    """離線模式：產生 SQL，不直接連接資料庫"""

    url = get_database_url()

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema="public",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """線上模式：連接 PostgreSQL 執行 Migration"""

    connectable = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10}
    )

    try:
        with connectable.connect() as connection:
            # Neon pooled connections reject search_path as a startup option.
            # Set it after the connection is established so all existing
            # unqualified migration DDL targets the restored public schema.
            connection.exec_driver_sql("SET search_path TO public")
            connection.commit()

            current_schema = connection.exec_driver_sql(
                "SELECT current_schema()"
            ).scalar_one()
            if current_schema != "public":
                raise RuntimeError(
                    f"Expected PostgreSQL current_schema() to be public; "
                    f"found {current_schema!r}"
                )

            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                version_table_schema="public",
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
