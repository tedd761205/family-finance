from fastapi.testclient import TestClient
from main import app


def test_category_management_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-categories"' in response.text
    assert 'id="categories-view"' in response.text
    assert 'id="category-form"' in response.text
    assert 'id="category-include-inactive"' in response.text


def test_category_management_ui_uses_scoped_existing_api():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert 'api("/categories?"+params.toString())' in javascript
    assert 'method:editingCategoryId?"PATCH":"POST"' in javascript
    assert 'method:"DELETE"' in javascript
    assert 'row.family_id===selectedFamilyId' in javascript


def test_category_management_keeps_system_categories_read_only():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert 'if(!row.is_system&&row.family_id===selectedFamilyId&&row.is_active)' in javascript
    assert 'row.is_system?"唯讀"' in javascript


def test_category_management_safe_rendering_and_confirmation():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert 'name.textContent=' in javascript
    assert 'window.confirm("確定停用' in javascript
    assert '歷史資料會保留' in javascript


def test_category_management_mobile_layout():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text
    assert ".category-admin-card" in css
    assert ".category-admin-actions" in css
