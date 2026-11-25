from fastapi.testclient import TestClient

from main import app


def test_bill_payment_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="bill-payments-view"' in response.text
    assert 'id="bill-payment-form"' in response.text


def test_bill_list_links_to_payment_refund_workspace():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'payments.textContent="付款／退款"' in javascript
    assert "showBillPayments(item)" in javascript


def test_bill_payment_ui_uses_existing_create_refund_and_void_apis():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/bill-payments?family_id="+selectedFamilyId' in javascript
    assert '"/bill-payments/"+billPaymentOriginalId+"/refund?family_id="+selectedFamilyId' in javascript
    assert 'api("/bill-payments/"+item.id+"?"+params.toString(),{method:"DELETE"})' in javascript


def test_bill_payment_ui_supports_cross_currency_rates_and_remaining_amount():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
        page = client.get("/").text

    assert "實際匯率" in javascript
    assert "exchange_rate" in javascript
    assert "預估帳戶" in javascript
    assert "實際帳戶" in javascript
    assert "匯差" in javascript
    assert "付款金額超過帳單未付餘額" in javascript
    assert "退款金額超過可退餘額" in javascript
    assert 'id="bill-payment-exchange-rate"' in page
    assert 'id="bill-payment-currency-summary"' in page


def test_bill_payment_ui_tracks_refund_balance_and_prevents_parent_void():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "function billPaymentRefundable(payment)" in javascript
    assert "hasActiveBillPaymentRefund(item)" in javascript
    assert "請先作廢退款紀錄" in javascript


def test_bill_payment_ui_refreshes_bill_balances_after_mutations():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert javascript.count("await loadBills();") >= 2
    assert "activeBillForPayments=updated" in javascript


def test_bill_payment_ui_has_voided_history_and_mobile_layout():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
        css = client.get("/static/styles.css").text

    assert 'params.set("include_voided","true")' in javascript
    assert ".bill-payments-panel" in css
    assert "@media(max-width:760px)" in css


def test_transaction_actions_do_not_reference_bill_payment_button():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    transactions = javascript.split("function renderTransactions()", 1)[1].split("async function loadTransactions()", 1)[0]
    assert "actions.append(edit,voidButton)" in transactions
    assert "actions.append(payments,edit,voidButton)" not in transactions


def test_bill_payment_action_is_attached_only_to_bill_cards():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    bills = javascript.split("function renderBills()", 1)[1].split("async function loadBills()", 1)[0]
    assert 'payments.textContent="付款／退款"' in bills
    assert "actions.append(payments,edit,voidButton)" in bills
