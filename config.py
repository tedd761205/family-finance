import os


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "development-key-change-before-production"
    )

    DATABASE_URL = os.environ.get("DATABASE_URL")

    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://",
            1
        )
