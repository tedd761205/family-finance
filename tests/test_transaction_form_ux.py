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

    assert "--page-bg: #f3f5f2" in styles
    assert "--surface: #fffefa" in styles
    assert "--accent: #58788b" in styles
    assert "--accent-warm: #c5a46a" in styles
    assert "background:" in styles
    assert "var(--danger-bg)" in styles
    assert "var(--success-bg)" in styles
    assert ".local-receipt-invoice-camera{display:grid" in styles
    assert "prefers-reduced-transparency: reduce" in styles


def test_warm_visual_theme_stylesheet_cache_is_refreshed():
    with TestClient(app) as client:
        page = client.get("/")

    assert page.status_code == 200
    assert '/static/styles.css?v=20261127-3' in page.text


def test_blue_jade_champagne_theme_keeps_warm_surfaces_and_distinct_semantic_colors():
    with TestClient(app) as client:
        styles = client.get("/static/styles.css").text

    assert "--accent-strong: #49697c" in styles
    assert "--accent-soft: #eaf1f4" in styles
    assert "--success-bg: #e5f2eb" in styles
    assert "--warning-bg: #fbf3e2" in styles
    assert "--danger-bg: #fce9e5" in styles
    assert "rgba(179, 204, 235, .30)" in styles
    assert "rgba(198, 165, 106, .20)" in styles
    assert "background: #7896a5" in styles
    assert "background: #c5a46a" in styles
    assert "--jade: #73ad99" in styles
    assert "--jade-strong: #2d7662" in styles
    assert "--jade-soft: #e8f3ed" in styles
    assert "--surface-muted: #edf3f8" in styles
    assert "--surface-soft: #e8f2ed" in styles


def test_scenic_background_is_available_and_accessibly_faded_behind_content():
    with TestClient(app) as client:
        scenery = client.get("/static/images/family-finance-scenery.svg")
        styles = client.get("/static/styles.css").text

    assert scenery.status_code == 200
    assert "<svg" in scenery.text
    assert "mountain" not in scenery.text.lower() or "viewBox" in scenery.text
    assert 'background-image: url("/static/images/family-finance-scenery.svg")' in styles
    assert "mask-image: linear-gradient" in styles
    assert "height: 430px" in styles
    assert "opacity: .62" in styles


def test_primary_action_uses_muted_blue_not_high_saturation_royal_blue():
    with TestClient(app) as client:
        styles = client.get("/static/styles.css").text

    assert "--accent: #58788b" in styles
    assert "--accent-strong: #49697c" in styles
    assert "background: #58788b" in styles
    assert "background: #49697c" in styles
    assert "background: #2456a6" not in styles
