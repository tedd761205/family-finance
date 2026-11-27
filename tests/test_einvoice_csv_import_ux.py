from fastapi.testclient import TestClient

from main import app


def test_einvoice_workspace_is_reachable_from_primary_navigation_and_shortcuts():
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/app.js")
        invoice_script = client.get("/static/invoice-csv-import.js")
        styles = client.get("/static/invoice-csv-import.css")

    assert page.status_code == 200
    assert script.status_code == 200
    assert invoice_script.status_code == 200
    assert styles.status_code == 200

    assert 'data-nav-key="invoice"' in page.text
    assert 'data-nav-target="open-einvoice-csv"' in page.text
    assert 'data-target="open-einvoice-csv"' in page.text
    assert 'id="einvoice-csv-view"' in page.text
    assert 'id="close-einvoice-csv"' in page.text
    assert '"open-einvoice-csv":"einvoice-csv-view"' in script.text
    assert "/static/app.js?v=20261127-3" in page.text
    assert "/static/invoice-csv-import.js?v=20261127-7" in page.text
    assert "/static/invoice-csv-import.css?v=20261127-4" in page.text


def test_einvoice_preview_has_clear_action_month_filter_and_pagination():
    with TestClient(app) as client:
        invoice_script = client.get("/static/invoice-csv-import.js")
        styles = client.get("/static/invoice-csv-import.css")

    assert invoice_script.status_code == 200
    assert styles.status_code == 200

    assert 'id="einvoice-csv-clear"' in invoice_script.text
    assert 'id="einvoice-csv-search"' in invoice_script.text
    assert 'id="einvoice-csv-search-clear"' in invoice_script.text
    assert "function invoiceMatchesSearch(invoice, query)" in invoice_script.text
    assert "invoice.merchantTaxId" in invoice_script.text
    assert 'invoice.date.replace(/-/g, "")' in invoice_script.text
    assert "invoice.items.map(item => item.itemName)" in invoice_script.text
    assert "const numericTerm = term.replace(/[^\\d.-]/g, \"\")" in invoice_script.text
    assert "amounts.some(amount => amount === amountCents)" in invoice_script.text
    assert 'id="einvoice-csv-month"' in invoice_script.text
    assert 'id="einvoice-csv-page-size"' in invoice_script.text
    assert 'id="einvoice-csv-pagination"' in invoice_script.text
    assert '<option value="10">10 張</option>' in invoice_script.text
    assert '<option value="20">20 張</option>' in invoice_script.text
    assert '<option value="50">50 張</option>' in invoice_script.text
    assert 'let pageSize = 10;' in invoice_script.text
    assert "function resetPreview(ask)" in invoice_script.text
    assert "function renderPagination(total)" in invoice_script.text
    assert "目前篩選條件沒有發票" in invoice_script.text

    assert ".einvoice-pagination" in styles.text
    assert ".einvoice-clear-button" in styles.text
    assert ".einvoice-search-row" in styles.text
    assert ".einvoice-search-label input" in styles.text
    assert "@media(max-width:760px)" in styles.text


def test_einvoice_saved_history_and_save_action_are_wired_to_family_scoped_apis():
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/app.js")
        invoice_script = client.get("/static/invoice-csv-import.js")
        styles = client.get("/static/invoice-csv-import.css")

    assert page.status_code == 200
    assert script.status_code == 200
    assert invoice_script.status_code == 200
    assert styles.status_code == 200

    assert 'data-nav-key="invoice"' in page.text
    assert 'data-permissions="invoices.view"' in page.text
    assert 'id="open-bank-imports"' in page.text
    assert 'id="open-bank-imports" type="button" data-permissions="imports.view"' in page.text
    assert "/static/app.js?v=20261127-3" in page.text
    assert "/static/invoice-csv-import.js?v=20261127-7" in page.text
    assert "/static/invoice-csv-import.css?v=20261127-4" in page.text

    assert "window.FamilyFinanceInvoiceBridge" in script.text
    assert "getFamilyId: () => selectedFamilyId" in script.text
    assert '"/electronic-invoices/imports?family_id="' in invoice_script.text
    assert '"/electronic-invoices?"' in invoice_script.text
    assert 'id="einvoice-csv-save"' in invoice_script.text
    assert 'id="einvoice-history-search"' in invoice_script.text
    assert 'id="einvoice-history-start"' in invoice_script.text
    assert 'id="einvoice-history-status"' in invoice_script.text
    assert 'id="einvoice-history-pagination"' in invoice_script.text
    assert 'function loadInvoiceHistoryDetail(invoiceId, detailHost, familyId, includeVoided)' in invoice_script.text
    assert 'params.set("include_voided", "true")' in invoice_script.text
    assert 'family-finance-family-changed' in invoice_script.text
    assert "previewSaved = true" in invoice_script.text
    assert "previewFamilyId = previewFamilyId ? String(previewFamilyId) : null" in invoice_script.text
    assert "家庭已切換，為避免發票存入錯誤家庭" in invoice_script.text
    assert "historyRequestSequence += 1" in invoice_script.text
    assert 'hasPermission("invoices.import")' in invoice_script.text
    assert "目前帳號只有查看權限，沒有匯入發票的權限" in invoice_script.text
    assert "function validatePreviewForSave()" in invoice_script.text
    assert "invoices.length > 1000" in invoice_script.text
    assert "totalItems > 20000" in invoice_script.text
    assert "invoice.items.length > 1000" in invoice_script.text
    assert "!/^\\d{8}$/.test(invoice.merchantTaxId)" in invoice_script.text
    assert invoice_script.text.index("const sequence = ++historyRequestSequence;") < invoice_script.text.index("if (!bridge || !familyId)")
    assert "不會自動新增收入或支出" in invoice_script.text

    assert ".einvoice-history-panel" in styles.text
    assert ".einvoice-history-filters" in styles.text
    assert ".einvoice-upload-actions" in styles.text
