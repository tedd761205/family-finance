from fastapi.testclient import TestClient

from main import app


def test_reconciliation_workspace_is_served_and_linked_from_home():
    with TestClient(app) as client:
        home = client.get("/")
        javascript = client.get("/static/reconciliation.js")
        css = client.get("/static/styles.css")

    assert home.status_code == 200
    assert 'id="open-bank-reconciliation"' in home.text
    assert 'id="bank-reconciliation-view"' in home.text
    assert 'id="reconciliation-session-form"' in home.text
    assert 'id="reconciliation-session-list"' in home.text
    assert 'id="reconciliation-detail-panel"' in home.text
    assert 'src="/static/reconciliation.js"' in home.text
    assert javascript.status_code == 200
    assert css.status_code == 200


def test_reconciliation_workspace_uses_authorized_api_for_lifecycle_and_matching():
    with TestClient(app) as client:
        javascript = client.get("/static/reconciliation.js").text

    assert '"/reconciliations/sessions?family_id="+selectedFamilyId' in javascript
    assert '"/reconciliations/sessions/"+sessionId+"?family_id="+selectedFamilyId+"&limit=500"' in javascript
    assert '"/reconciliations/sessions/"+sessionId+"/suggestions?family_id="+selectedFamilyId' in javascript
    assert '"/reconciliations/sessions/"+activeReconciliationSession.id+"/matches?family_id="+selectedFamilyId' in javascript
    assert '"/reconciliations/sessions/"+activeReconciliationSession.id+"/exclude?family_id="+selectedFamilyId' in javascript
    assert '"/reconciliations/sessions/"+activeReconciliationSession.id+"/complete?family_id="+selectedFamilyId' in javascript
    assert '"/reconciliations/sessions/"+activeReconciliationSession.id+"/reopen?family_id="+selectedFamilyId' in javascript
    assert '"/reconciliations/sessions/"+activeReconciliationSession.id+"/matches/"+matchId+"/void?family_id="+selectedFamilyId' in javascript
    assert '"/reconciliations/sessions/"+activeReconciliationSession.id+"/exclusions/"+exclusionId+"/void?family_id="+selectedFamilyId' in javascript


def test_reconciliation_workspace_supports_manual_transaction_search_and_safe_text_rendering():
    with TestClient(app) as client:
        javascript = client.get("/static/reconciliation.js").text

    assert '"/transactions?family_id="+selectedFamilyId+"&account_id="+session.account_id' in javascript
    assert 'select.add(new Option' in javascript
    assert 'node.textContent=value??""' in javascript
    assert "innerHTML" not in javascript


def test_reconciliation_workspace_discloses_that_suggestions_do_not_auto_match():
    with TestClient(app) as client:
        home = client.get("/").text
        javascript = client.get("/static/reconciliation.js").text

    assert "候選建議只供參考，必須由使用者確認配對" in home
    assert "配對不會建立、修改或作廢帳務交易" in home
    assert "automatic" not in javascript.lower() or "automatic_matches_created" not in javascript


def test_reconciliation_workspace_has_mobile_first_layout():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".reconciliation-session-card" in css
    assert ".reconciliation-kpis" in css
    assert ".reconciliation-candidate-card" in css
    assert "@media(max-width:760px)" in css
    assert ".reconciliation-manual-select" in css
