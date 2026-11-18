from fastapi.testclient import TestClient

from main import app


def test_transfer_management_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-transfers"' in response.text
    assert 'id="transfers-view"' in response.text
    assert 'id="transfers-list"' in response.text
    assert 'id="transfer-form"' in response.text


def test_transfer_workspace_uses_existing_transfer_and_account_apis():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/transfers?"+transferQuery())' in javascript
    assert 'api("/accounts?family_id="+selectedFamilyId)' in javascript
    assert 'method:"POST"' in javascript
    assert 'method:"PATCH"' in javascript
    assert 'method:"DELETE"' in javascript
    assert 'from_account_id:from.id' in javascript
    assert 'to_account_id:to.id' in javascript


def test_transfer_workspace_validates_currency_and_fee_account():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "轉出與轉入帳戶幣別必須相同" in javascript
    assert "有手續費時必須指定扣款帳戶" in javascript
    assert "fee_account_id:fee>0?Number(feeAccountId):null" in javascript


def test_transfer_void_action_uses_specialized_transfer_endpoint():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/transfers/"+item.id+"?family_id="+selectedFamilyId,{method:"DELETE"})' in javascript
    assert "一併作廢轉出、轉入及手續費交易" in javascript


def test_transfer_workspace_has_mobile_responsive_styles():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".transfers-panel" in css
    assert "@media(max-width:760px)" in css
