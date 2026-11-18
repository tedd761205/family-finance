from fastapi.testclient import TestClient

from main import app


def test_account_management_workspace_is_available_after_login_view():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-accounts"' in response.text
    assert 'id="accounts-view"' in response.text
    assert 'id="accounts-list"' in response.text
    assert 'id="account-form"' in response.text
    assert 'id="opening-form"' in response.text


def test_account_management_frontend_supports_all_account_types():
    with TestClient(app) as client:
        response = client.get("/")

    for account_type in (
        "bank",
        "time_deposit",
        "cash",
        "credit_card",
        "e_wallet",
        "other",
    ):
        assert f'value="{account_type}"' in response.text


def test_account_management_frontend_uses_existing_protected_apis():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert '"/accounts?family_id="+selectedFamilyId' in javascript
    assert '"/accounts/balances?family_id="+selectedFamilyId' in javascript
    assert 'method:"POST"' in javascript
    assert 'method:"PATCH"' in javascript
    assert 'method:"DELETE"' in javascript
    assert 'transaction_type:"opening_balance"' in javascript
    assert "此帳戶已有有效期初餘額" in javascript
    assert "selectedFamilyId" in javascript


def test_account_management_styles_include_mobile_layout():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".accounts-list" in css
    assert ".account-card" in css
    assert "@media(max-width:760px)" in css
