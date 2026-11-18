from fastapi.testclient import TestClient

from main import app


def test_bill_management_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-bills"' in response.text
    assert 'id="bills-view"' in response.text
    assert 'id="bill-form"' in response.text


def test_bill_ui_uses_existing_bill_api_endpoints():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/bills?"+billQuery())' in javascript
    assert 'api("/bills?family_id="+selectedFamilyId' in javascript
    assert 'method:"PATCH"' in javascript
    assert 'method:"DELETE"' in javascript


def test_bill_ui_supports_amount_components_and_period_validation():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "原始金額必須大於 0" in javascript
    assert "折扣金額不可大於原始金額加稅額" in javascript
    assert "帳單期間起日與迄日必須同時填寫" in javascript


def test_bill_ui_displays_backend_payment_statuses():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    for status in ("unpaid", "partially_paid", "paid", "overdue", "voided"):
        assert status in javascript
    assert "remaining_amount" in javascript
    assert "paid_amount" in javascript


def test_bill_void_uses_reason_and_warns_about_active_payments():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'params.set("reason",reason.trim())' in javascript
    assert "需先處理付款紀錄" in javascript


def test_bill_currency_is_locked_after_payment_history():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'include_voided=true&limit=200' in javascript
    assert '$("bill-currency").disabled=editingBillPaymentHistory' in javascript
    assert '$("bill-currency").disabled=editingBillPaymentHistory' in javascript


def test_bill_workspace_has_mobile_responsive_styles():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".bills-panel" in css
    assert ".bill-card-top" in css
    assert "@media(max-width:760px)" in css
