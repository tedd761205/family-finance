from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image


@pytest.fixture(scope="session", autouse=True)
def ensure_attachment_schema():
    from app.database import Base, engine
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def attachment_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from main import app
    from app.database import engine, get_db
    from app.services import attachment_storage

    monkeypatch.setenv("JWT_SECRET_KEY", "g01-06-attachment-test-secret-key-32-bytes")
    stored = {}

    def fake_upload(key, content, content_type, sha256):
        stored[key] = (content, content_type, sha256)

    def fake_download(key):
        return stored[key][0]

    def fake_delete(key):
        stored.pop(key, None)

    monkeypatch.setattr(attachment_storage, "upload_object", fake_upload)
    monkeypatch.setattr(attachment_storage, "download_object", fake_download)
    monkeypatch.setattr(attachment_storage, "delete_object", fake_delete)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, stored
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_permissions():
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.models.permission import Permission
    from app.permission_catalog import PERMISSION_CATALOG

    with Session(engine) as db:
        existing = {item.code for item in db.query(Permission).all()}
        for item in PERMISSION_CATALOG:
            if item["code"] not in existing:
                db.add(Permission(**item))
        db.commit()


def _setup_family(client, suffix):
    _seed_permissions()
    email = f"g0106-{suffix}@example.com"
    password = "G01-06-attachment-test-password-123!"
    registered = client.post("/auth/register", json={
        "email": email, "password": password, "display_name": "G-01-06 附件測試",
    })
    assert registered.status_code == 201, registered.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    family = client.post("/families", headers=headers, json={
        "name": f"G-01-06 附件測試家庭 {suffix}", "currency": "TWD",
    })
    assert family.status_code == 201, family.text
    family_id = family.json()["family_id"]

    bill = client.post(f"/bills?family_id={family_id}", headers=headers, json={
        "bill_number": f"ATT-{suffix[:8]}", "title": "測試水電帳單",
        "bill_date": "2026-11-01", "due_date": "2026-11-30",
        "original_amount": "800.0000", "tax_amount": "0",
        "discount_amount": "0", "currency_code": "TWD",
    })
    assert bill.status_code == 201, bill.text
    return headers, family_id, bill.json()["id"]


def _png_bytes(color=(30, 90, 150, 255)):
    image = Image.new("RGBA", (24, 16), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_upload_list_download_and_void_attachment(attachment_client):
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.models.attachment import Attachment
    from app.models.audit_log import AuditLog

    client, stored = attachment_client
    headers, family_id, bill_id = _setup_family(client, uuid4().hex)
    image = _png_bytes()

    uploaded = client.post(
        f"/attachments?family_id={family_id}&bill_id={bill_id}",
        headers=headers,
        files={"file": ("../../帳單照片.png", image, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    item = uploaded.json()
    assert item["bill_id"] == bill_id
    assert item["transaction_id"] is None
    assert item["content_type"] == "image/png"
    assert item["file_size"] > 0
    assert "/" not in item["original_filename"]
    assert len(item["sha256"]) == 64
    assert len(stored) == 1

    listed = client.get(
        f"/attachments?family_id={family_id}&bill_id={bill_id}",
        headers=headers,
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    downloaded = client.get(
        f"/attachments/{item['id']}/content?family_id={family_id}",
        headers=headers,
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "image/png"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.content == stored[next(iter(stored))][0]

    with Session(engine) as db:
        audit_downloads = db.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.family_id == family_id,
            AuditLog.entity_type == "attachment",
            AuditLog.action == "download",
        ))
        assert audit_downloads == 1

    voided = client.delete(
        f"/attachments/{item['id']}?family_id={family_id}&reason=duplicate",
        headers=headers,
    )
    assert voided.status_code == 200, voided.text
    assert voided.json()["attachment"]["is_voided"] is True
    assert len(stored) == 1  # 作廢只保留檔案，不刪除財務證據

    hidden = client.get(
        f"/attachments/{item['id']}/content?family_id={family_id}",
        headers=headers,
    )
    assert hidden.status_code == 404

    with Session(engine) as db:
        saved = db.get(Attachment, item["id"])
        assert saved is not None and saved.is_voided
        void_logs = db.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.family_id == family_id,
            AuditLog.entity_type == "attachment",
            AuditLog.action == "void",
        ))
        assert void_logs == 1


def test_rejects_fake_image_and_oversized_upload(attachment_client):
    client, stored = attachment_client
    headers, family_id, bill_id = _setup_family(client, uuid4().hex)

    fake = client.post(
        f"/attachments?family_id={family_id}&bill_id={bill_id}",
        headers=headers,
        files={"file": ("fake.jpg", b"this is not an image", "image/jpeg")},
    )
    assert fake.status_code == 422
    assert stored == {}

    too_large = client.post(
        f"/attachments?family_id={family_id}&bill_id={bill_id}",
        headers=headers,
        files={"file": ("large.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
    )
    assert too_large.status_code == 413
    assert stored == {}


def test_rejects_cross_family_bill_and_requires_one_parent(attachment_client):
    client, stored = attachment_client
    headers_a, family_a, bill_a = _setup_family(client, f"{uuid4().hex}-a")
    _, family_b, bill_b = _setup_family(client, f"{uuid4().hex}-b")
    image = _png_bytes()

    cross_family = client.post(
        f"/attachments?family_id={family_a}&bill_id={bill_b}",
        headers=headers_a,
        files={"file": ("receipt.png", image, "image/png")},
    )
    assert cross_family.status_code == 404
    assert stored == {}

    missing_parent = client.post(
        f"/attachments?family_id={family_a}",
        headers=headers_a,
        files={"file": ("receipt.png", image, "image/png")},
    )
    assert missing_parent.status_code == 422
    assert stored == {}

    both_parents = client.post(
        f"/attachments?family_id={family_a}&bill_id={bill_a}&transaction_id=1",
        headers=headers_a,
        files={"file": ("receipt.png", image, "image/png")},
    )
    assert both_parents.status_code == 422
    assert stored == {}
