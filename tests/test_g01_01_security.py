from decimal import Decimal
from types import SimpleNamespace
from typing import get_args

import pytest
from fastapi import HTTPException
from sqlalchemy import Numeric

from app.models.audit_log import AuditLog
from app.models.credit_card_payment import CreditCardPayment
from app.routers import account_report
from app.services.audit_log import add_audit_log


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


def test_credit_card_payment_uses_decimal_and_numeric_20_4():
    amount_annotation = CreditCardPayment.__annotations__["amount"]
    assert Decimal in get_args(amount_annotation)

    amount_column = CreditCardPayment.__table__.c.amount
    assert isinstance(amount_column.type, Numeric)
    assert amount_column.type.precision == 20
    assert amount_column.type.scale == 4


def test_add_audit_log_adds_json_safe_record_without_committing():
    db = FakeSession()

    record = add_audit_log(
        db,
        family_id=7,
        actor_user_id=11,
        action="update",
        entity_type="account",
        entity_id=23,
        old_values={"amount": Decimal("10.2500")},
        new_values={"amount": Decimal("20.5000")},
    )

    assert db.added == [record]
    assert isinstance(record, AuditLog)
    assert record.family_id == 7
    assert record.actor_user_id == 11
    assert record.old_values == {"amount": "10.2500"}
    assert record.new_values == {"amount": "20.5000"}


def test_account_report_requires_own_account_scope(monkeypatch):
    class FakeQuery:
        def __init__(self):
            self.filters = []

        def filter(self, *conditions):
            self.filters.extend(str(item) for item in conditions)
            return self

        def first(self):
            return None

    class FakeDB:
        def __init__(self):
            self.query_object = FakeQuery()

        def query(self, model):
            assert model.__name__ == "Account"
            return self.query_object

    monkeypatch.setattr(
        account_report,
        "require_permission",
        lambda **kwargs: (None, [SimpleNamespace(id=1)]),
    )
    monkeypatch.setattr(
        account_report,
        "require_data_scope",
        lambda **kwargs: "own",
    )
    monkeypatch.setattr(
        account_report,
        "calculate_account_summary",
        lambda **kwargs: pytest.fail("must not calculate an inaccessible account"),
    )

    db = FakeDB()
    with pytest.raises(HTTPException) as exc:
        account_report.get_account_summary(
            family_id=7,
            account_id=23,
            current_user=SimpleNamespace(id=11),
            db=db,
        )

    assert exc.value.status_code == 404
    assert any("created_by" in condition for condition in db.query_object.filters)
