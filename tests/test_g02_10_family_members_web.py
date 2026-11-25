from fastapi.testclient import TestClient

from main import app


def test_family_members_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-family-members"' in response.text
    assert 'id="family-members-view"' in response.text
    assert 'id="family-member-invite-form"' in response.text
    assert 'id="family-invite-link-panel"' in response.text
    assert 'id="family-invitations-list"' in response.text
    assert 'id="family-members-list"' in response.text


def test_family_members_ui_calls_permission_checked_endpoint():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/families/" + selectedFamilyId + "/members")' in javascript
    assert 'api("/families/" + selectedFamilyId + "/invitations", {' in javascript
    assert 'body: JSON.stringify({email})' in javascript
    assert 'api("/families/invitations/accept"' in javascript
    assert 'copy-family-invite-link' in javascript


def test_family_members_endpoint_is_registered_and_secured():
    schema = app.openapi()
    operation = schema["paths"]["/families/{family_id}/members"]["get"]

    assert "HTTPBearer" in str(operation.get("security", []))
    assert operation["responses"]["200"]["description"] == "Successful Response"


def test_family_members_ui_refreshes_after_family_switch():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'if(!$("family-members-view").classList.contains("hidden")){await loadFamilyMembers();await loadFamilyInvitations();}' in javascript


def test_family_members_ui_has_mobile_styles():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".family-member-card" in css
    assert ".family-member-actions" in css
    assert ".member-invite-form" in css
    assert "@media(max-width:760px)" in css


def test_family_member_removal_endpoint_is_registered_and_secured():
    schema = app.openapi()
    operation = schema["paths"]["/families/{family_id}/members/{family_member_id}"]["delete"]

    assert "HTTPBearer" in str(operation.get("security", []))
    assert operation["responses"]["200"]["description"] == "Successful Response"


def test_family_member_removal_ui_explains_soft_removal_and_reinvite():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert "使用者帳號、既有帳務及歷史紀錄都會保留" in javascript
    assert "重新邀請" in javascript
    assert "members.remove" in client.get("/static/app.js").text or "member.can_remove" in javascript
