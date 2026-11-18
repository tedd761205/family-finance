from uuid import uuid4

import pytest


@pytest.fixture
def g0107_client(monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from app.database import Base, engine, get_db
    from app import models  # noqa: F401
    from app.models.permission import Permission
    from app.permission_catalog import PERMISSION_CATALOG
    from app.services import attachment_storage
    from main import app

    Base.metadata.create_all(bind=engine)
    monkeypatch.setenv("JWT_SECRET_KEY", "g01-07-collaboration-test-secret-key-32-bytes")
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

    with Session(engine) as db:
        existing = {item.code for item in db.query(Permission).all()}
        for item in PERMISSION_CATALOG:
            if item["code"] not in existing:
                db.add(Permission(**item))
        db.commit()

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, stored
    finally:
        app.dependency_overrides.pop(get_db, None)


def _family(client):
    suffix = uuid4().hex
    email = f"g0107-{suffix}@example.com"
    password = "G01-07-test-password-123!"
    registered = client.post("/auth/register", json={
        "email": email, "password": password, "display_name": "G-01-07 測試",
    })
    assert registered.status_code == 201, registered.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = client.post("/families", headers=headers, json={
        "name": f"G-01-07 測試家庭 {suffix}", "currency": "TWD",
    })
    assert created.status_code == 201, created.text
    return headers, created.json()["family_id"]


def test_export_template_version_conflict_publish_run_download_and_notification(g0107_client):
    client, stored = g0107_client
    headers, family_id = _family(client)
    config = {"dataset": "transactions", "columns": ["id", "amount", "currency_code"]}

    created = client.post(
        f"/exports/templates?family_id={family_id}", headers=headers,
        json={"name": "家庭交易匯出", "description": "測試範本", "config": config},
    )
    assert created.status_code == 201, created.text
    template = created.json()
    template_id = template["id"]
    assert template["status"] == "draft"
    assert template["version"] == 1

    published = client.post(
        f"/exports/templates/{template_id}/publish?family_id={family_id}&expected_version=1",
        headers=headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    updated_config = {"dataset": "transactions", "columns": ["id", "occurred_on", "amount"]}
    updated = client.put(
        f"/exports/templates/{template_id}?family_id={family_id}", headers=headers,
        json={"name": "家庭交易匯出新版", "description": "已手動合併", "config": updated_config,
              "expected_version": 1},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["status"] == "draft"

    stale = client.put(
        f"/exports/templates/{template_id}?family_id={family_id}", headers=headers,
        json={"name": "舊版覆蓋", "description": None, "config": config, "expected_version": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "EXPORT_TEMPLATE_VERSION_CONFLICT"
    assert stale.json()["detail"]["latest_version"] == 2

    versions = client.get(
        f"/exports/templates/{template_id}/versions?family_id={family_id}", headers=headers,
    )
    assert versions.status_code == 200
    assert len(versions.json()["versions"]) == 2

    published_v2 = client.post(
        f"/exports/templates/{template_id}/publish?family_id={family_id}&expected_version=2",
        headers=headers,
    )
    assert published_v2.status_code == 200, published_v2.text

    run = client.post(
        f"/exports/templates/{template_id}/run?family_id={family_id}", headers=headers,
    )
    assert run.status_code == 201, run.text
    run_item = run.json()
    assert run_item["status"] == "succeeded"
    assert run_item["template_version"] == 2
    assert run_item["sha256"] and run_item["file_size"] > 0
    assert len(stored) == 1

    downloaded = client.get(
        f"/exports/runs/{run_item['id']}/download?family_id={family_id}", headers=headers,
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content.startswith(b"\xef\xbb\xbf")
    assert b"id,occurred_on,amount" in downloaded.content

    notifications = client.get(f"/notifications?family_id={family_id}", headers=headers)
    assert notifications.status_code == 200, notifications.text
    assert notifications.json()["unread"] >= 1
    notification = notifications.json()["notifications"][0]
    marked = client.post(
        f"/notifications/{notification['id']}/read?family_id={family_id}", headers=headers,
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["read_at"] is not None

    dashboard = client.get(f"/exports/dashboard?family_id={family_id}", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["timezone"] == "Asia/Taipei"
    assert dashboard.json()["status_counts"]["succeeded"] >= 1


def test_scheduled_export_requires_published_template_and_is_taipei_time(g0107_client):
    client, _ = g0107_client
    headers, family_id = _family(client)
    created = client.post(
        f"/exports/templates?family_id={family_id}", headers=headers,
        json={"name": "定期帳單", "description": None,
              "config": {"dataset": "bills", "columns": ["id", "title", "bill_date"]}},
    )
    template_id = created.json()["id"]
    rejected = client.post(
        f"/exports/schedules?family_id={family_id}", headers=headers,
        json={"template_id": template_id, "name": "每週匯出", "frequency": "weekly", "weekday": 1},
    )
    assert rejected.status_code == 409

    publish = client.post(
        f"/exports/templates/{template_id}/publish?family_id={family_id}&expected_version=1",
        headers=headers,
    )
    assert publish.status_code == 200
    schedule = client.post(
        f"/exports/schedules?family_id={family_id}", headers=headers,
        json={"template_id": template_id, "name": "每週匯出", "frequency": "weekly",
              "weekday": 1, "local_hour": 9, "local_minute": 30},
    )
    assert schedule.status_code == 201, schedule.text
    assert schedule.json()["timezone"] == "Asia/Taipei"
    assert schedule.json()["next_run_at"].endswith("+00:00")
    disabled = client.post(
        f"/exports/schedules/{schedule.json()['id']}/disable?family_id={family_id}",
        headers=headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False



def test_due_schedule_worker_uses_latest_published_version_and_rechecks_access(g0107_client):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy.orm import Session
    from app.database import engine
    from app.models.export_template import ExportSchedule, ExportRun
    from app.routers.g01_07 import process_due_exports

    client, stored = g0107_client
    headers, family_id = _family(client)
    created = client.post(
        f"/exports/templates?family_id={family_id}", headers=headers,
        json={"name": "排程範本", "description": None,
              "config": {"dataset": "bills", "columns": ["id", "title"]}},
    )
    template_id = created.json()["id"]
    published = client.post(
        f"/exports/templates/{template_id}/publish?family_id={family_id}&expected_version=1",
        headers=headers,
    )
    assert published.status_code == 200
    schedule = client.post(
        f"/exports/schedules?family_id={family_id}", headers=headers,
        json={"template_id": template_id, "name": "到期排程", "frequency": "daily",
              "local_hour": 8, "local_minute": 0},
    )
    assert schedule.status_code == 201, schedule.text
    schedule_id = schedule.json()["id"]

    with Session(engine) as db:
        item = db.query(ExportSchedule).filter(ExportSchedule.id == schedule_id).one()
        item.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        result = process_due_exports(db)
        assert result == {"checked": 1, "succeeded": 1, "failed": 0, "disabled": 0}

    with Session(engine) as db:
        run = db.query(ExportRun).filter(
            ExportRun.family_id == family_id, ExportRun.schedule_id == schedule_id,
        ).one()
        assert run.status == "succeeded"
        assert run.template_version == 1
        assert run.template_snapshot["data_scope"] == "family"
        assert run.sha256 and run.file_size > 0
    assert len(stored) == 1
