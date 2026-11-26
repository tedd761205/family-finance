from fastapi.testclient import TestClient

from main import app


def test_recent_transaction_defaults_are_saved_only_after_create_and_scoped_by_family():
    with TestClient(app) as client:
        script = client.get("/static/app.js").text
        page = client.get("/")

    assert page.status_code == 200
    assert "TRANSACTION_DEFAULTS_KEY_PREFIX" in script
    assert '"family_finance_recent_transaction_defaults_v1:"' in script
    assert "sessionStorage.getItem(TRANSACTION_DEFAULTS_KEY_PREFIX + selectedFamilyId)" in script
    assert "sessionStorage.setItem(" in script
    assert "rememberRecentTransactionDefaults(account.id, type, categoryId)" in script
    assert "transactionAccounts.some" in script
    assert 'item.is_active !== false' in script


def test_recent_transaction_category_default_is_separate_for_income_and_expense():
    with TestClient(app) as client:
        script = client.get("/static/app.js").text
        page = client.get("/")

    assert page.status_code == 200
    assert "saved.categories[type]" in script
    assert "item.category_type === type" in script
    assert 'populateTransactionCategories($("transaction-type").value);\n  applyRecentTransactionDefaults();' in script
    assert "/static/app.js?v=20261126-2" in page.text


def test_transaction_defaults_storage_errors_do_not_block_transaction_entry():
    with TestClient(app) as client:
        script = client.get("/static/app.js").text

    start = script.index("function rememberRecentTransactionDefaults(")
    end = script.index("function applyRecentTransactionDefaults()", start)
    remember_function = script[start:end]

    assert "try {" in remember_function
    assert "catch (_error)" in remember_function
    assert "Remembering defaults is optional" in remember_function
