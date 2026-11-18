from fastapi.testclient import TestClient

from main import app


def test_family_role_management_workspace_is_served():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'id="open-family-roles"' in response.text
    assert 'id="family-roles-view"' in response.text
    assert 'id="family-role-form"' in response.text
    assert 'id="family-role-members"' in response.text


def test_role_management_routes_are_registered_and_authenticated():
    schema = app.openapi()
    paths = schema["paths"]
    expected = [
        ("/families/{family_id}/roles", "get"),
        ("/families/{family_id}/roles", "post"),
        ("/families/{family_id}/roles/{role_id}", "patch"),
        ("/families/{family_id}/roles/{role_id}", "delete"),
        ("/families/{family_id}/permissions", "get"),
        ("/families/{family_id}/members/{family_member_id}/roles", "put"),
    ]
    for path, method in expected:
        assert method in paths[path]
        assert paths[path][method].get("security")


def test_role_editor_uses_existing_permission_and_scope_contracts():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'api("/families/" + selectedFamilyId + "/roles")' in javascript
    assert 'permission_codes:permissionCodes' in javascript
    assert 'data_scopes:dataScopes' in javascript
    assert 'method:"PUT", body:JSON.stringify({role_ids:roleIds})' in javascript


def test_system_roles_are_marked_protected_in_ui():
    with TestClient(app) as client:
        javascript = client.get("/static/app.js").text

    assert 'if (!role.is_system)' in javascript
    assert '"（系統預設）"' in javascript
    assert 'role.is_system ?' in javascript


def test_role_management_has_mobile_layout():
    with TestClient(app) as client:
        css = client.get("/static/styles.css").text

    assert ".role-permission-groups" in css
    assert ".family-role-member-controls" in css
    assert "@media(max-width:760px)" in css
