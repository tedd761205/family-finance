from fastapi.testclient import TestClient

from main import app


def test_home_serves_family_finance_web_interface():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "家庭記帳系統" in response.text
    assert 'id="auth-form"' in response.text
    assert 'id="app-view"' in response.text


def test_frontend_assets_are_served():
    with TestClient(app) as client:
        css = client.get("/static/styles.css")
        javascript = client.get("/static/app.js")

    assert css.status_code == 200
    assert "auth-layout" in css.text
    assert javascript.status_code == 200
    assert "/auth/login" in javascript.text
    assert "/families/mine" in javascript.text


def test_app_config_exposes_only_public_google_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "public-client-id.apps.googleusercontent.com")

    with TestClient(app) as client:
        response = client.get("/app-config")

    assert response.status_code == 200
    assert response.json() == {
        "google_client_id": "public-client-id.apps.googleusercontent.com"
    }
