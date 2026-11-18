from fastapi.testclient import TestClient

from main import app


def test_audit_log_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-audit-logs"' in response.text
    assert 'id="audit-logs-view"' in response.text
    assert 'id="audit-log-filter-form"' in response.text
    assert 'id="audit-logs-list"' in response.text


def test_audit_log_route_is_registered_and_authenticated():
    schema = app.openapi()
    operation = schema["paths"]["/families/{family_id}/audit-logs"]["get"]

    assert operation.get("security")
    assert "start_date" in str(operation.get("parameters", []))
    assert "end_date" in str(operation.get("parameters", []))


def test_audit_log_ui_uses_family_scoped_read_only_endpoint():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert '"/audit-logs?" + params.toString()' in javascript
    assert 'result.scope === "family"' in javascript
    audit_viewer = javascript[javascript.index("async function loadAuditLogs()"):javascript.index("G-02-13")]
    assert 'method:"DELETE"' not in audit_viewer


def test_audit_log_ui_displays_old_and_new_values_as_text():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'oldPre.textContent = JSON.stringify(record.old_values, null, 2)' in javascript
    assert 'nextPre.textContent = JSON.stringify(record.new_values, null, 2)' in javascript


def test_audit_log_viewer_has_mobile_layout():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".audit-log-filters" in css
    assert ".audit-log-value-grid" in css
    assert "@media(max-width:760px)" in css
