from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.attachment_storage import (
    AttachmentStorageNotConfigured,
    check_storage_connection,
)


def main() -> int:
    try:
        check_storage_connection()
    except AttachmentStorageNotConfigured as exc:
        print(f"Storage configuration incomplete: {exc}")
        return 2
    except Exception:
        # Never print SDK exception details because they may contain request metadata.
        print("Storage connection check failed. Verify Render environment variables and R2 token permissions.")
        return 1
    print("Private attachment storage connection check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
