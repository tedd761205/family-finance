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
    assert "/static/app.js?v=20261126-3" in page.text


def test_transaction_defaults_storage_errors_do_not_block_transaction_entry():
    with TestClient(app) as client:
        script = client.get("/static/app.js").text

    start = script.index("function rememberRecentTransactionDefaults(")
    end = script.index("function applyRecentTransactionDefaults()", start)
    remember_function = script[start:end]

    assert "try {" in remember_function
    assert "catch (_error)" in remember_function
    assert "Remembering defaults is optional" in remember_function



def test_date_filters_reject_reversed_ranges_before_requesting_data():
    with TestClient(app) as client:
        script = client.get("/static/app.js").text

    assert "function validateDateRange(startFieldId, endFieldId, noticeTarget, sectionLabel)" in script
    assert "start <= end" in script
    assert "結束日期不可早於開始日期" in script
    assert 'validateDateRange(\n    "transaction-filter-start"' in script
    assert 'validateDateRange("transfer-filter-start","transfer-filter-end"' in script
    assert 'validateDateRange("credit-payment-filter-start","credit-payment-filter-end"' in script
    assert 'validateDateRange("bill-filter-start","bill-filter-end"' in script


def test_transaction_filter_has_clear_action_and_contextual_no_results_message():
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/app.js").text

    assert page.status_code == 200
    assert 'id="clear-transaction-filters"' in page.text
    assert 'id="transaction-empty-title"' in page.text
    assert 'id="transaction-empty-description"' in page.text
    assert "找不到符合條件的紀錄" in script
    assert "目前日期、類型或帳戶條件沒有相符資料" in script
    assert 'clear-transaction-filters").addEventListener("click",clearTransactionFilters)' in script
    assert "function clearTransactionFilters()" in script
    assert 'id="clear-transaction-filters"' in page.text
    assert "/static/app.js?v=20261126-3" in page.text



def test_clear_filter_remains_available_when_date_range_validation_fails():
    with TestClient(app) as client:
        script = client.get("/static/app.js").text

    start = script.index("async function loadTransactions()")
    end = script.index("async function showTransactions()", start)
    loader = script[start:end]

    assert loader.index('$("clear-transaction-filters").disabled = !transactionFiltersActive();') < loader.index("validateDateRange(")
    assert "if (!validateDateRange(" in loader
    assert '$(endFieldId)?.focus();' in script



def test_warm_family_theme_uses_cream_sage_palette_with_readable_semantic_states():
    with TestClient(app) as client:
        styles = client.get("/static/styles.css").text

    assert "--page-bg: #f5efe3" in styles
    assert "--surface: #fffdf7" in styles
    assert "--accent: #347b56" in styles
    assert "--accent-warm: #c87552" in styles
    assert "background:" in styles
    assert "var(--danger-bg)" in styles
    assert "var(--success-bg)" in styles
    assert ".local-receipt-invoice-camera{display:grid" in styles
    assert "prefers-reduced-transparency: reduce" in styles


def test_warm_visual_theme_stylesheet_cache_is_refreshed():
    with TestClient(app) as client:
        page = client.get("/")

    assert page.status_code == 200
    assert '/static/styles.css?v=20261127-1' in page.text


def test_brighter_warm_theme_keeps_warm_neutrals_and_distinct_semantic_colors():
    with TestClient(app) as client:
        styles = client.get("/static/styles.css").text

    assert "--accent-strong: #285f43" in styles
    assert "--accent-soft: #e1eee2" in styles
    assert "--success-bg: #e2f0e3" in styles
    assert "--warning-bg: #fff0d5" in styles
    assert "--danger-bg: #fce7e3" in styles
    assert "rgba(220, 178, 124, .34)" in styles
    assert "rgba(146, 181, 143, .30)" in styles
    assert "background: #5f9866" in styles
    assert "background: #cf805d" in styles
