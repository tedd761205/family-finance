from decimal import Decimal

from app.models.bank_import import BankImportRow
from app.models.reconciliation import ReconciliationMatch, ReconciliationSession
from app.permission_catalog import PERMISSION_CATALOG
from app.role_catalog import ADMIN_PERMISSIONS, BOOKKEEPER_PERMISSIONS, FINANCE_PERMISSIONS


def test_reconciliation_models_register_expected_tables():
    assert ReconciliationSession.__tablename__ == "reconciliation_sessions"
    assert ReconciliationMatch.__tablename__ == "reconciliation_matches"


def test_reconciliation_session_enforces_family_account_and_period():
    constraints = {item.name for item in ReconciliationSession.__table__.constraints}
    assert "uq_reconciliation_sessions_family_id_id" in constraints
    assert "uq_reconciliation_sessions_family_id_account_batch" in constraints
    assert "fk_reconciliation_sessions_family_account" in constraints
    assert "fk_reconciliation_sessions_family_account_batch" in constraints
    assert "ck_reconciliation_sessions_period" in constraints
    assert "ck_reconciliation_sessions_status" in constraints
    assert "ck_reconciliation_sessions_counts" in constraints


def test_reconciliation_session_prevents_duplicate_active_periods_and_batches():
    indexes = {item.name: item for item in ReconciliationSession.__table__.indexes}
    assert indexes["uq_reconciliation_sessions_active_period"].unique is True
    assert indexes["uq_reconciliation_sessions_active_period"].dialect_options["postgresql"]["where"] is not None
    assert indexes["uq_reconciliation_sessions_source_batch"].unique is True


def test_reconciliation_match_has_family_scoped_foreign_keys_and_allocation_checks():
    constraints = {item.name for item in ReconciliationMatch.__table__.constraints}
    assert "fk_reconciliation_matches_family_session_account_batch" in constraints
    assert "fk_reconciliation_matches_family_import_row" in constraints
    assert "fk_reconciliation_matches_family_account_transaction" in constraints
    assert "ck_reconciliation_matches_amount_positive" in constraints
    assert "ck_reconciliation_matches_void_metadata" in constraints


def test_reconciliation_match_prevents_active_transaction_double_matching():
    indexes = {item.name: item for item in ReconciliationMatch.__table__.indexes}
    index = indexes["uq_reconciliation_matches_active_transaction"]
    assert index.unique is True
    assert index.dialect_options["postgresql"]["where"] is not None


def test_bank_import_rows_expose_composite_key_for_session_batch_integrity():
    constraints = {item.name for item in BankImportRow.__table__.constraints}
    assert "uq_bank_import_rows_family_batch_id" in constraints


def test_reconciliation_money_uses_decimal_numeric_columns():
    assert str(ReconciliationSession.__table__.c.opening_balance.type) == "NUMERIC(20, 4)"
    assert str(ReconciliationMatch.__table__.c.allocated_amount.type) == "NUMERIC(20, 4)"
    assert Decimal("1200.0000") + Decimal("800.0000") == Decimal("2000.0000")


def test_reconciliation_permissions_are_available_to_intended_default_roles():
    codes = {item["code"] for item in PERMISSION_CATALOG}
    assert {"reconciliation.exclude", "reconciliation.reopen"} <= codes
    assert "reconciliation.exclude" in FINANCE_PERMISSIONS
    assert "reconciliation.exclude" in BOOKKEEPER_PERMISSIONS
    assert "reconciliation.reopen" in ADMIN_PERMISSIONS
    assert "reconciliation.reopen" not in FINANCE_PERMISSIONS
