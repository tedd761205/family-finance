from fastapi.testclient import TestClient

from main import app


def test_recurring_bill_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-recurring-bills"' in response.text
    assert 'id="recurring-bills-view"' in response.text
    assert 'id="recurring-bill-form"' in response.text


def test_recurring_bill_ui_uses_existing_api_endpoints():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/recurring-bills?"+recurringBillQuery())' in javascript
    assert 'api("/recurring-bills?family_id="+selectedFamilyId' in javascript
    assert '"/recurring-bills/"+editingRecurringBillId+"?family_id="+selectedFamilyId' in javascript
    assert '"/recurring-bills/"+item.id+"?family_id="+selectedFamilyId' in javascript


def test_recurring_bill_ui_supports_only_backend_frequencies():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
        html = client.get("/").text

    assert 'weekly:"每週",monthly:"每月",yearly:"每年"' in javascript
    assert 'value="weekly"' in html
    assert 'value="monthly"' in html
    assert 'value="yearly"' in html


def test_recurring_bill_ui_validates_dates_and_amounts():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "結束日期不可早於開始日期" in javascript
    assert "下次產生日期不可早於開始日期" in javascript
    assert "折扣金額不可大於原始金額加稅額" in javascript


def test_recurring_bill_generate_uses_through_date_and_refreshes_bills():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert '"/recurring-bills/"+item.id+"/generate?family_id="+selectedFamilyId' in javascript
    assert "through_date=" in javascript
    assert 'if(!$("bills-view").classList.contains("hidden"))await loadBills();' in javascript


def test_recurring_bill_deactivation_is_soft_and_preserves_generated_bills():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'method:"DELETE"' in javascript
    assert "既有帳單保留" in javascript
    assert "已產生的帳單不會刪除" in javascript


def test_recurring_bill_workspace_has_mobile_responsive_styles():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".recurring-bills-panel" in css
    assert ".recurring-bill-card" in css
    assert "@media(max-width:760px)" in css


def test_recurring_bill_generate_date_uses_iso_date_validation():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert r"/^\d{4}-\d{2}-\d{2}$/" in javascript
    assert r"/^\\d{4}-\\d{2}-\\d{2}$/" not in javascript
