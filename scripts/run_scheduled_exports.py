"""Run due family export schedules from a dedicated scheduled worker.

The deployment scheduler should invoke this script periodically. It does not
start a web server and does not print database credentials or exported data.
"""
from app.database import SessionLocal
from app.routers.g01_07 import process_due_exports


def main() -> None:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL 尚未設定")
    with SessionLocal() as db:
        result = process_due_exports(db, limit=25)
    print(
        "scheduled_exports "
        f"checked={result['checked']} "
        f"succeeded={result['succeeded']} "
        f"failed={result['failed']} "
        f"disabled={result['disabled']}"
    )


if __name__ == "__main__":
    main()
