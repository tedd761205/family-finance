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




def test_family_theme_uses_soft_jade_primary_and_readable_semantic_states():
    with TestClient(app) as client:
        styles = client.get("/static/styles.css").text

    active_theme = styles.rsplit("Soft scenic family theme", 1)[-1]
    assert "--page-bg: #f3f5f2" in active_theme
    assert "--surface: #fffefa" in active_theme
    assert "--accent: #3f826a" in active_theme
    assert "--accent-strong: #326f5a" in active_theme
    assert "--accent-warm: #c5a46a" in active_theme
    assert "var(--danger-bg)" in active_theme
    assert "var(--success-bg)" in active_theme
    assert ".local-receipt-invoice-camera{display:grid" in styles
    assert "prefers-reduced-transparency: reduce" in active_theme


def test_soft_jade_space_theme_stylesheet_cache_is_refreshed():
    with TestClient(app) as client:
        page = client.get("/")

    assert page.status_code == 200
    assert '/static/styles.css?v=20261127-4' in page.text


def test_soft_jade_theme_keeps_champagne_as_a_small_accent_and_semantic_colors():
    with TestClient(app) as client:
        styles = client.get("/static/styles.css").text

    active_theme = styles.rsplit("Soft scenic family theme", 1)[-1]
    assert "--accent: #3f826a" in active_theme
    assert "--accent-strong: #326f5a" in active_theme
    assert "--accent-soft: #e8f3ed" in active_theme
    assert "--accent-warm: #c5a46a" in active_theme
    assert "--success-bg: #e5f2eb" in active_theme
    assert "--warning-bg: #fbf3e2" in active_theme
    assert "--danger-bg: #fce9e5" in active_theme
    assert "--jade: #73ad99" in active_theme
    assert "--jade-strong: #2d7662" in active_theme
    assert "--jade-soft: #e8f3ed" in active_theme


def test_original_space_background_is_available_and_accessibly_faded_behind_content():
    with TestClient(app) as client:
        space = client.get("/static/images/family-finance-space.svg")
        styles = client.get("/static/styles.css").text

    active_theme = styles.rsplit("Soft scenic family theme", 1)[-1]
    assert space.status_code == 200
    assert "<svg" in space.text
    assert '<radialGradient id="nebula"' in space.text
    assert "spiral galaxy" in space.text
    assert 'background-image: url("/static/images/family-finance-space.svg")' in active_theme
    assert "mask-image: linear-gradient" in active_theme
    assert "height: 430px" in active_theme
    assert "opacity: .56" in active_theme


def test_primary_action_uses_soft_jade_with_champagne_reserved_for_details():
    with TestClient(app) as client:
        styles = client.get("/static/styles.css").text

    active_theme = styles.rsplit("Soft scenic family theme", 1)[-1]
    assert "--accent: #3f826a" in active_theme
    assert "--accent-strong: #326f5a" in active_theme
    assert "background: #3f826a" in active_theme
    assert "background: #326f5a" in active_theme
    assert "background: #c5a46a" not in active_theme

