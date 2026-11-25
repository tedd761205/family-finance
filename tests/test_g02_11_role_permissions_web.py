from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.routers.roles as roles_router
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
        ("/families/{family_id}/my-permissions", "get"),
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

def test_current_family_permissions_are_the_union_of_assigned_roles(monkeypatch):
    family_member = SimpleNamespace(id=41)
    roles = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    monkeypatch.setattr(
        roles_router,
        "get_active_family_member",
        lambda **kwargs: family_member,
    )
    monkeypatch.setattr(
        roles_router,
        "get_active_family_roles",
        lambda **kwargs: roles,
    )
    monkeypatch.setattr(
        roles_router,
        "_actor_permission_codes",
        lambda db, assigned_roles: {"accounts.view", "transactions.view", "reports.view"}
        if assigned_roles == roles
        else set(),
    )

    result = roles_router.list_my_permissions(
        family_id=9,
        current_user=SimpleNamespace(id=7),
        db=object(),
    )

    assert result == {
        "success": True,
        "permission_codes": ["accounts.view", "reports.view", "transactions.view"],
    }


def test_more_tools_have_searchable_categories_and_permission_metadata():
    with TestClient(app) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text
        css = client.get("/static/styles.css").text

    assert 'id="more-tools-search"' in html
    assert 'data-category="accounts"' in html
    assert 'data-category="bank"' in html
    assert 'data-permissions="reconciliation.view"' in html
    assert '"/my-permissions"' in javascript
    assert "applyFamilyNavigationPermissions" in javascript
    assert ".more-category-picker" in css
    assert "var(--visible-nav-items,5)" in css

