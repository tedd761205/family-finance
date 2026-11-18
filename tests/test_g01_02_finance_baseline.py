"""G-01-02 regression tests for balance, permission scopes and payment validation."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dependencies.permissions import get_data_scope, require_data_scope
from app.models.account import Account
from app.models.role_data_scope import RoleDataScope
from app.models.transaction import Transaction
from app.services.account_balance import calculate_account_balance
from app.routers.transfer import validate_transfer_accounts
from app.routers.credit_card_payment import validate_payment_accounts


class FakeQuery:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(str(condition) for condition in conditions)
        return self

    def group_by(self, *columns):
        return self

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.last_query = None

    def query(self, *columns):
        self.last_query = FakeQuery(self.rows)
        return self.last_query


def make_account(account_type="bank", family_id=7, account_id=10):
    return SimpleNamespace(
        id=account_id,
        family_id=family_id,
        name="測試帳戶",
        account_type=account_type,
        currency_code="TWD",
        is_active=True,
    )


def test_asset_account_balance_includes_opening_income_and_expense():
    db = FakeDB([
        SimpleNamespace(transaction_type="opening_balance", total_amount=Decimal("500.0000"), transaction_count=1),
        SimpleNamespace(transaction_type="income", total_amount=Decimal("100.2500"), transaction_count=2),
        SimpleNamespace(transaction_type="expense", total_amount=Decimal("30.1250"), transaction_count=3),
    ])

    result = calculate_account_balance(db, make_account())

    assert result["opening_balance"] == Decimal("500.0000")
    assert result["total_income"] == Decimal("100.2500")
    assert result["total_expense"] == Decimal("30.1250")
    assert result["balance"] == Decimal("570.1250")
    assert result["transaction_count"] == 6


def test_credit_card_balance_treats_positive_amount_as_debt():
    db = FakeDB([
        SimpleNamespace(transaction_type="opening_balance", total_amount=Decimal("200.0000"), transaction_count=1),
        SimpleNamespace(transaction_type="expense", total_amount=Decimal("80.0000"), transaction_count=2),
        SimpleNamespace(transaction_type="income", total_amount=Decimal("30.0000"), transaction_count=1),
    ])

    result = calculate_account_balance(db, make_account(account_type="credit_card"))

    assert result["balance"] == Decimal("250.0000")


def test_balance_filters_by_creator_when_own_scope_is_requested():
    db = FakeDB([
        SimpleNamespace(transaction_type="income", total_amount=Decimal("50.0000"), transaction_count=1),
    ])

    calculate_account_balance(db, make_account(), created_by=123)

    assert any("created_by" in condition for condition in db.last_query.filters)
    assert any("is_voided" in condition for condition in db.last_query.filters)


def test_data_scope_prefers_family_over_own_for_multiple_roles():
    db = FakeDB([("own",), ("family",)])
    roles = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    assert get_data_scope(db, roles, family_id=7, resource="transactions") == "family"


def test_data_scope_returns_own_when_no_family_scope_exists():
    db = FakeDB([("own",)])
    roles = [SimpleNamespace(id=1)]

    assert get_data_scope(db, roles, family_id=7, resource="transactions") == "own"


def test_data_scope_denies_when_no_scope_is_configured():
    db = FakeDB([])
    roles = [SimpleNamespace(id=1)]

    with pytest.raises(PermissionError):
        require_data_scope(db, roles, family_id=7, resource="transactions")


def test_data_scope_returns_none_when_member_has_no_roles():
    db = FakeDB([])

    assert get_data_scope(db, [], family_id=7, resource="transactions") is None
    assert db.last_query is None


def test_transfer_rejects_same_source_and_destination_account():
    with pytest.raises(HTTPException) as exc:
        validate_transfer_accounts(
            FakeDB(), 7, 10, 10, "TWD", Decimal("0"), None
        )

    assert exc.value.status_code == 400


def test_transfer_accepts_same_currency_accounts_and_fee_account():
    accounts = [
        make_account(account_id=10),
        make_account(account_id=11, family_id=7),
        make_account(account_id=12, family_id=7),
    ]
    db = FakeDB(accounts)

    result = validate_transfer_accounts(
        db, 7, 10, 11, "TWD", Decimal("5.0000"), 12
    )

    assert set(result) == {10, 11, 12}


def test_transfer_rejects_missing_fee_account():
    with pytest.raises(HTTPException) as exc:
        validate_transfer_accounts(
            FakeDB([make_account(account_id=10), make_account(account_id=11)]),
            7, 10, 11, "TWD", Decimal("5.0000"), None
        )

    assert exc.value.status_code == 400


def test_transfer_rejects_currency_mismatch():
    accounts = [
        make_account(account_id=10),
        SimpleNamespace(
            id=11, family_id=7, name="外幣帳戶", account_type="bank",
            currency_code="USD", is_active=True,
        ),
    ]

    with pytest.raises(HTTPException) as exc:
        validate_transfer_accounts(
            FakeDB(accounts), 7, 10, 11, "TWD", Decimal("0"), None
        )

    assert exc.value.status_code == 400


def test_transfer_rejects_inactive_or_foreign_family_account():
    with pytest.raises(HTTPException) as exc:
        validate_transfer_accounts(
            FakeDB([
                SimpleNamespace(id=10, family_id=7, currency_code="TWD", is_active=True),
                SimpleNamespace(id=11, family_id=7, currency_code="TWD", is_active=False),
            ]),
            7, 10, 11, "TWD", Decimal("0"), None
        )

    assert exc.value.status_code == 400


def test_credit_card_payment_accepts_bank_to_credit_card():
    accounts = [
        SimpleNamespace(id=10, family_id=7, account_type="bank", currency_code="TWD", is_active=True),
        SimpleNamespace(id=11, family_id=7, account_type="credit_card", currency_code="TWD", is_active=True),
    ]

    result = validate_payment_accounts(FakeDB(accounts), 7, 10, 11, "TWD")

    assert set(result) == {10, 11}


@pytest.mark.parametrize(
    "source_type,target_type,currency",
    [
        ("credit_card", "credit_card", "TWD"),
        ("bank", "bank", "TWD"),
        ("bank", "credit_card", "USD"),
    ],
)
def test_credit_card_payment_rejects_invalid_account_types_or_currency(
    source_type, target_type, currency
):
    accounts = [
        SimpleNamespace(id=10, family_id=7, account_type=source_type, currency_code="TWD", is_active=True),
        SimpleNamespace(id=11, family_id=7, account_type=target_type, currency_code="TWD", is_active=True),
    ]

    with pytest.raises(HTTPException) as exc:
        validate_payment_accounts(FakeDB(accounts), 7, 10, 11, currency)

    assert exc.value.status_code == 400


def test_credit_card_payment_rejects_same_account():
    with pytest.raises(HTTPException) as exc:
        validate_payment_accounts(FakeDB(), 7, 10, 10, "TWD")

    assert exc.value.status_code == 400


def test_credit_card_payment_rejects_inactive_account():
    accounts = [
        SimpleNamespace(id=10, family_id=7, account_type="bank", currency_code="TWD", is_active=True),
        SimpleNamespace(id=11, family_id=7, account_type="credit_card", currency_code="TWD", is_active=False),
    ]

    with pytest.raises(HTTPException) as exc:
        validate_payment_accounts(FakeDB(accounts), 7, 10, 11, "TWD")

    assert exc.value.status_code == 400
