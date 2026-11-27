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
    assert "/static/app.js?v=20261127-2" in page.text
    assert "/static/invoice-csv-import.js?v=20261127-3" in page.text
    assert "/static/invoice-csv-import.css?v=20261127-3" in page.text


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
    assert "invoice.items.map(item => item.itemName)" in invoice_script.text
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
