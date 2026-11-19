from fastapi.testclient import TestClient
from main import app


def test_bank_import_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert 'id="open-bank-imports"' in response.text
    assert 'id="bank-imports-view"' in response.text
    assert 'id="bank-import-inspect-form"' in response.text
    assert 'id="bank-import-mapping"' in response.text
    assert 'id="bank-import-confirm"' in response.text


def test_bank_import_ui_defaults_to_statement_only_confirmation():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert '"/imports/inspect?family_id="+selectedFamilyId' in javascript
    assert '"/imports/batches?family_id="+selectedFamilyId+"&account_id="+$("bank-import-account").value' in javascript
    assert '"/imports/batches/"+selectedImportBatchId+"/confirm?family_id="+selectedFamilyId' in javascript
    assert "尚未新增正式交易" in javascript
    assert "確認只匯入銀行對帳明細" in javascript
    assert "&create_transactions=" in javascript
    assert 'id="bank-import-create-transactions"' in client.get("/").text


def test_bank_import_ui_uses_text_content_and_responsive_preview():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
        css = client.get("/static/styles.css").text
    assert "td.textContent=String(value)" in javascript
    assert ".import-preview-table" in css
    assert ".import-batch-card" in css


def test_bank_import_ui_supports_required_and_optional_column_mapping():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
    assert '["date","交易日期",true]' in javascript
    assert '["amount","金額",true]' in javascript
    assert '["description","交易說明",true]' in javascript
    assert '["external_reference","銀行交易序號",false]' in javascript
