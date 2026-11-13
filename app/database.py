import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# 從 Render 環境變數讀取 Neon 連線資訊
DATABASE_URL = os.getenv("DATABASE_URL")

# 統一使用 psycopg 3 驅動程式
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1
        )

    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1
        )


# 建立資料庫連線引擎
engine = (
    create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10}
    )
    if DATABASE_URL
    else None
)


# 建立資料表基礎類別
class Base(DeclarativeBase):
    pass


# 建立資料庫 Session
SessionLocal = (
    sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    if engine
    else None
)


# 資料庫連線測試
def check_database_connection():
    if engine is None:
        raise RuntimeError("DATABASE_URL 尚未設定")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return True


# 提供資料庫 Session
def get_db():
    if SessionLocal is None:
        raise RuntimeError("資料庫尚未設定")

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
