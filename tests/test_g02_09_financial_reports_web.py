from fastapi.testclient import TestClient

from main import app


def test_financial_reports_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-reports"' in response.text
    assert 'id="reports-view"' in response.text
    assert 'id="monthly-report-summary"' in response.text
    assert 'id="yearly-report-list"' in response.text
    assert 'id="category-report-list"' in response.text


def test_financial_reports_ui_uses_existing_report_endpoints():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert '"/reports/monthly-summary?family_id="+selectedFamilyId' in javascript
    assert '"/reports/yearly-summary?family_id="+selectedFamilyId' in javascript
    assert '"/reports/category-summary?"+categoryParams.toString()' in javascript


def test_financial_reports_ui_supports_currency_separation():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
        html = client.get("/").text

    assert "function reportCurrencies(...groups)" in javascript
    assert "function reportAmountMap(rows)" in javascript
    assert "不同幣別分開顯示" in html


def test_financial_reports_ui_renders_monthly_income_expense_and_net():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "function renderMonthlyReport(data)" in javascript
    assert '["總收入",income.get(currency)||0,"income"]' in javascript
    assert '["總支出",expense.get(currency)||0,"expense"]' in javascript
    assert '["淨收支",net.get(currency)||0,"net"]' in javascript


def test_financial_reports_ui_renders_yearly_monthly_trends():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "function renderYearlyReport(data)" in javascript
    assert "data.monthly_reports||[]" in javascript
    assert "yearly-bar-fill expense" in javascript


def test_financial_reports_ui_renders_category_percentages():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "function renderCategoryReport(data)" in javascript
    assert "item.percentage" in javascript
    assert "item.transaction_count" in javascript


def test_financial_reports_ui_validates_date_range_and_year():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "報表年份必須介於 2000 至 2100" in javascript
    assert "分類開始日期不可晚於結束日期" in javascript


def test_financial_reports_ui_refreshes_after_family_switch():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'if(!$("reports-view").classList.contains("hidden")){await loadFinancialReports();}' in javascript


def test_financial_reports_ui_has_mobile_responsive_styles():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".reports-panel" in css
    assert ".report-filter-grid" in css
    assert "@media(max-width:760px)" in css


def test_financial_reports_can_export_monthly_yearly_and_category_csv():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text
        html = client.get("/").text

    assert 'id="export-monthly-report"' in html
    assert 'id="export-yearly-report"' in html
    assert 'id="export-category-report"' in html
    assert "function downloadMonthlyReportCsv()" in javascript
    assert "function downloadYearlyReportCsv()" in javascript
    assert "function downloadCategoryReportCsv()" in javascript
    assert "text/csv;charset=utf-8" in javascript
    assert "\\uFEFF" in javascript
    assert "reportCsvCell" in javascript
    assert "setReportExportAvailability(false)" in javascript


def test_financial_report_csv_keeps_currency_rows_separate_and_includes_category_details():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert '["期間","幣別","總收入","總支出","淨收支"]' in javascript
    assert '["年度","期間","幣別","總收入","總支出","淨收支"]' in javascript
    assert '["收支類型","分類名稱","幣別","金額","交易筆數","同幣別類型占比(%)"]' in javascript
    assert "reportCurrencies(data.total_income,data.total_expense,data.net_amount)" in javascript
