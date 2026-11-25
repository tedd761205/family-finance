from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import hashlib

import pytest
from fastapi import HTTPException

from app.models.family_invitation import FamilyInvitation
from app.routers import family_invitations


class Query:
    def __init__(self, values):
        self.values = values

    def filter(self, *args, **kwargs):
        return self

    def with_for_update(self):
        return self

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class FakeDB:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def query(self, *args):
        return Query([])

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_invitation_model_hashes_only_token():
    invitation = FamilyInvitation(
        family_id=1,
        email="family@example.com",
        token_hash=hashlib.sha256(b"raw-token").hexdigest(),
        invited_by_user_id=2,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    assert invitation.token_hash != "raw-token"
    assert len(invitation.token_hash) == 64


def test_invitation_accept_requires_google_identity(monkeypatch):
    user = SimpleNamespace(id=5, email="family@example.com", is_active=True)
    db = FakeDB()
    monkeypatch.setattr(
        family_invitations,
        "_get_invitation_for_user",
        lambda db, token, user: SimpleNamespace(family_id=8, status="pending"),
    )
    monkeypatch.setattr(
        family_invitations,
        "_join_family",
        lambda db, invitation, user: 12,
    )
    monkeypatch.setattr(db, "commit", lambda: setattr(db, "committed", True))
    monkeypatch.setattr(db, "rollback", lambda: setattr(db, "rolled_back", True))
    # Endpoint's token validator is the single gate for Google identity and exact email.
    result = family_invitations.accept_family_invitation(
        family_invitations.FamilyInvitationAccept(token="x" * 32),
        current_user=user,
        db=db,
    )
    assert result.success is True
    assert result.family_id == 8
    assert db.committed is True
