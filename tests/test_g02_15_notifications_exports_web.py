from fastapi.testclient import TestClient
from main import app


def test_notifications_and_exports_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-notifications-exports"' in response.text
    assert 'id="notifications-exports-view"' in response.text
    assert 'id="notifications-list"' in response.text
    assert 'id="export-template-form"' in response.text
    assert 'id="export-schedule-form"' in response.text
    assert 'id="export-runs-list"' in response.text


def test_notifications_use_current_user_scoped_api_and_text_rendering():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert '"/notifications?family_id="+selectedFamilyId+"&limit=100"' in javascript
    assert '"/notifications/"+item.id+"/read?family_id="+selectedFamilyId' in javascript
    assert 'title.textContent=item.title' in javascript
    assert 'desc.textContent=item.body||""' in javascript


def test_export_templates_use_whitelisted_config_and_optimistic_version():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert 'config:{dataset:$("export-template-dataset").value,columns}' in javascript
    assert 'body.expected_version=editingExportTemplate.version' in javascript
    assert '"/exports/templates/"+item.id+"/publish?family_id="+selectedFamilyId+"&expected_version="+item.version' in javascript
    assert '"/exports/templates/"+item.id+"/disable?family_id="+selectedFamilyId+"&expected_version="+item.version' in javascript


def test_exports_run_download_and_schedule_use_existing_authorized_endpoints():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert '"/exports/templates/"+item.id+"/run?family_id="+selectedFamilyId' in javascript
    assert '"/exports/runs?family_id="+selectedFamilyId+"&limit=100"' in javascript
    assert '"/exports/runs/"+id+"/download?family_id="+selectedFamilyId' in javascript
    assert '"/exports/schedules?family_id="+selectedFamilyId' in javascript
    assert '"/exports/schedules?family_id="+selectedFamilyId' in javascript
    assert '"/exports/schedules/"+item.id+"/disable?family_id="+selectedFamilyId' in javascript


def test_export_schedule_ui_discloses_worker_dependency_and_taipei_timezone():
    with TestClient(app) as client:
        response = client.get("/")
        javascript = client.get("/static/app.js").text
    assert "定時自動執行仍需啟用排程 Worker" in response.text
    assert "Asia/Taipei" in response.text
    assert 'local_hour:Number($("export-schedule-hour").value)' in javascript


def test_notifications_exports_mobile_layout():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text
    assert ".notification-admin-card" in css
    assert ".export-admin-card" in css
    assert ".export-columns" in css
