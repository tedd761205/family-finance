from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.user_identity import UserIdentity
from app.routers import auth


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement):
        return FakeResult(self.results.pop(0))

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def get(self, model, user_id):
        return self.user_by_id


def setup_google(monkeypatch, email="family@example.com", sub="google-sub-123"):
    monkeypatch.setattr(
        auth,
        "verify_google_token_or_raise",
        lambda token: {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": "Family User",
        },
    )
    monkeypatch.setattr(
        auth,
        "create_user_token",
        lambda user: SimpleNamespace(
            access_token=f"token-for-{user.id}",
            token_type="bearer",
            expires_in=1200,
        ),
    )


def test_google_recovery_binds_verified_matching_email(monkeypatch):
    setup_google(monkeypatch)
    existing_user = SimpleNamespace(
        id=42,
        email="family@example.com",
        is_active=True,
    )
    db = FakeDB([None, existing_user])

    result = auth.recover_existing_account_with_google(
        auth.GoogleLoginRequest(id_token="verified-google-token"),
        db=db,
    )

    assert result.access_token == "token-for-42"
    assert len(db.added) == 1
    identity = db.added[0]
    assert isinstance(identity, UserIdentity)
    assert identity.user_id == 42
    assert identity.provider == "google"
    assert identity.provider_subject == "google-sub-123"
    assert identity.email == "family@example.com"
    assert db.committed is True
    assert db.rolled_back is False


def test_google_recovery_rejects_different_email(monkeypatch):
    setup_google(monkeypatch, email="attacker@example.com")
    db = FakeDB([None, None])

    with pytest.raises(HTTPException) as exc:
        auth.recover_existing_account_with_google(
            auth.GoogleLoginRequest(id_token="verified-google-token"),
            db=db,
        )

    assert exc.value.status_code == 404
    assert db.added == []
    assert db.committed is False


def test_google_recovery_does_not_rebind_identity_owned_by_another_user(monkeypatch):
    setup_google(monkeypatch, email="family@example.com")
    existing_identity = SimpleNamespace(user_id=99)
    other_user = SimpleNamespace(
        id=99,
        email="another@example.com",
        is_active=True,
    )
    db = FakeDB([existing_identity])
    db.user_by_id = other_user

    with pytest.raises(HTTPException) as exc:
        auth.recover_existing_account_with_google(
            auth.GoogleLoginRequest(id_token="verified-google-token"),
            db=db,
        )

    assert exc.value.status_code == 409
    assert db.added == []
    assert db.committed is False
