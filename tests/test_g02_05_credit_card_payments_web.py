from fastapi.testclient import TestClient

from main import app


def test_credit_card_payment_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-credit-card-payments"' in response.text
    assert 'id="credit-card-payments-view"' in response.text
    assert 'id="credit-payment-form"' in response.text


def test_credit_card_payment_ui_uses_existing_api_endpoints():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/credit-card-payments?"+creditCardPaymentQuery())' in javascript
    assert 'api("/credit-card-payments?family_id="+selectedFamilyId' in javascript
    assert 'method:"PATCH"' in javascript
    assert 'method:"DELETE"' in javascript
    assert 'payload.from_account_id=source.id' in javascript
    assert 'payload.credit_card_account_id=card.id' in javascript


def test_credit_card_payment_ui_limits_account_types_and_currency():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert '["bank","cash","e_wallet"].includes(account.account_type)' in javascript
    assert 'account.account_type==="credit_card"' in javascript
    assert "扣款帳戶與信用卡帳戶幣別必須相同" in javascript


def test_credit_card_payment_api_accepts_existing_e_wallet_account_type():
    with TestClient(app) as client:
        source = client.get("/openapi.json").json()

    assert "/credit-card-payments" in source["paths"]
    from pathlib import Path
    router = Path("app/routers/credit_card_payment.py").read_text(encoding="utf-8")
    assert '"e_wallet"' in router
    assert '"e_payment"' not in router


def test_credit_card_payment_void_uses_specialized_endpoint_and_preserves_history():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/credit-card-payments/"+item.id+"?family_id="+selectedFamilyId,{method:"DELETE"})' in javascript
    assert "信用卡繳款及相關交易已作廢" in javascript


def test_credit_card_payment_workspace_has_mobile_responsive_styles():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".credit-card-payments-panel" in css
    assert "@media(max-width:760px)" in css


def test_credit_card_payment_date_filters_cover_full_taiwan_local_days():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "paymentDateTime(value, endOfDay=false)" in javascript
    assert 'T23:59:59+08:00' in javascript
    assert 'params.set("end_date",paymentDateTime(end,true))' in javascript
