from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy.orm import Session


@pytest.fixture(scope="session", autouse=True)
def ensure_test_schema():
    from app.database import Base, engine
    from app import models  # noqa: F401

    if engine is None:
        raise RuntimeError("DATABASE_URL is required for the isolated E2E database")
    Base.metadata.create_all(bind=engine)


def _seed_permissions():
    from app.database import engine
    from app.models.permission import Permission
    from app.permission_catalog import PERMISSION_CATALOG

    with Session(engine) as db:
        existing = {item.code for item in db.query(Permission).all()}
        for item in PERMISSION_CATALOG:
            if item["code"] not in existing:
                db.add(Permission(**item))
        db.commit()


def _png_bytes():
    image = Image.new("RGB", (64, 48), (35, 95, 145))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_real_neon_storage_attachment_and_ocr_flow(monkeypatch):
    """Exercise FastAPI attachment/OCR APIs against real Neon object storage.

    The database is a disposable PostgreSQL service in GitHub Actions. Only the
    OCR provider is stubbed; upload, download, integrity checks and cleanup use
    the configured private Neon Object Storage bucket.
    """
    import os

    from fastapi.testclient import TestClient

    from app.database import engine, get_db
    from app.models.attachment import Attachment
    from app.services import attachment_storage, ocr_tasks
    from main import app

    required = (
        "ATTACHMENT_STORAGE_ENDPOINT_URL",
        "ATTACHMENT_STORAGE_REGION",
        "ATTACHMENT_STORAGE_BUCKET",
        "ATTACHMENT_STORAGE_ACCESS_KEY_ID",
        "ATTACHMENT_STORAGE_SECRET_ACCESS_KEY",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.fail("Missing required storage environment variables: " + ", ".join(missing))

    monkeypatch.setenv("JWT_SECRET_KEY", "g01-06-real-storage-e2e-test-secret-32-bytes")
    _seed_permissions()

    def override_get_db():
        with Session(engine) as db:
            yield db

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    object_key = None

    monkeypatch.setattr(
        ocr_tasks,
        "recognize_image",
        lambda content, content_type: {
            "text": "測試帳單\n應繳金額：1,280",
            "suggested_fields": {"amount_candidate": "1280"},
        },
    )

    try:
        with TestClient(app) as client:
            suffix = uuid4().hex
            email = f"real-storage-{suffix}@example.com"
            password = "G01-06-real-storage-test-password-123!"

            registered = client.post("/auth/register", json={
                "email": email,
                "password": password,
                "display_name": "真實儲存整合測試",
            })
            assert registered.status_code == 201, registered.text

            login = client.post("/auth/login", json={
                "email": email,
                "password": password,
            })
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            family_response = client.post("/families", headers=headers, json={
                "name": f"Neon 真實儲存測試家庭 {suffix}",
                "currency": "TWD",
            })
            assert family_response.status_code == 201, family_response.text
            family_id = family_response.json()["family_id"]

            bill_response = client.post(f"/bills?family_id={family_id}", headers=headers, json={
                "bill_number": f"NEON-{suffix[:12]}",
                "title": "Neon Object Storage 整合測試帳單",
                "bill_date": "2026-11-18",
                "due_date": "2026-11-30",
                "original_amount": "1280.0000",
                "tax_amount": "0",
                "discount_amount": "0",
                "currency_code": "TWD",
            })
            assert bill_response.status_code == 201, bill_response.text
            bill_id = bill_response.json()["id"]

            upload = client.post(
                f"/attachments?family_id={family_id}&bill_id={bill_id}",
                headers=headers,
                files={"file": ("neon-e2e.png", _png_bytes(), "image/png")},
            )
            assert upload.status_code == 201, upload.text
            attachment_id = upload.json()["id"]
            assert upload.json()["sha256"]

            with Session(engine) as db:
                attachment = db.query(Attachment).filter(
                    Attachment.id == attachment_id,
                    Attachment.family_id == family_id,
                ).one()
                object_key = attachment.object_key
                expected_digest = attachment.sha256

            # The API must retrieve the exact bytes from the real private bucket.
            download = client.get(
                f"/attachments/{attachment_id}/content?family_id={family_id}",
                headers=headers,
            )
            assert download.status_code == 200, download.text
            assert download.content == _png_bytes()
            assert download.headers["cache-control"] == "private, no-store"

            # OCR reads the same real object and verifies its SHA-256 before
            # invoking the stubbed provider. Human confirmation remains explicit.
            task_create = client.post(
                f"/ocr/tasks?family_id={family_id}&attachment_id={attachment_id}",
                headers=headers,
            )
            assert task_create.status_code == 201, task_create.text
            task_id = task_create.json()["task"]["id"]

            processed = client.post(
                f"/ocr/tasks/{task_id}/process?family_id={family_id}",
                headers=headers,
            )
            assert processed.status_code == 200, processed.text
            assert processed.json()["task"]["status"] == "succeeded"
            assert processed.json()["task"]["suggested_fields"]["amount_candidate"] == "1280"

            confirmed = client.post(
                f"/ocr/tasks/{task_id}/confirm?family_id={family_id}",
                headers=headers,
            )
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["task"]["status"] == "confirmed"

            # Voiding hides the attachment from API reads but intentionally
            # preserves the underlying financial evidence object.
            voided = client.delete(
                f"/attachments/{attachment_id}?family_id={family_id}&reason=e2e-test",
                headers=headers,
            )
            assert voided.status_code == 200, voided.text
            assert voided.json()["attachment"]["is_voided"] is True
            assert attachment_storage.download_object(object_key)
            assert expected_digest == upload.json()["sha256"]

            hidden = client.get(
                f"/attachments/{attachment_id}/content?family_id={family_id}",
                headers=headers,
            )
            assert hidden.status_code == 404
    finally:
        # This is a disposable test object created by this test only. Production
        # attachment voiding never deletes the original financial evidence.
        if object_key:
            attachment_storage.delete_object(object_key)
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
