from datetime import date
from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.recurring_bill import RecurringBillCreate, RecurringBillUpdate
from app.services.recurring_bill import advance_date


def test_weekly_schedule_advances_by_interval():
    assert advance_date(date(2026, 11, 18), "weekly", 2) == date(2026, 12, 2)


def test_monthly_schedule_clamps_month_end_without_skipping_month():
    assert advance_date(date(2026, 1, 31), "monthly", 1) == date(2026, 2, 28)
    assert advance_date(date(2026, 1, 31), "monthly", 2) == date(2026, 3, 31)


def test_yearly_schedule_handles_leap_day():
    assert advance_date(date(2024, 2, 29), "yearly", 1) == date(2025, 2, 28)


def test_unsupported_frequency_is_rejected():
    with pytest.raises(ValueError):
        advance_date(date(2026, 1, 1), "daily", 1)


def test_recurring_bill_create_defaults_next_run_and_validates_amounts():
    payload = RecurringBillCreate(
        title="  電費  ",
        frequency="monthly",
        start_date=date(2026, 11, 1),
        original_amount=Decimal("1000.0000"),
    )
    assert payload.title == "電費"
    assert payload.next_run_date is None
    assert payload.currency_code == "TWD"


def test_recurring_bill_rejects_invalid_date_range():
    with pytest.raises(ValidationError):
        RecurringBillCreate(
            title="電費",
            frequency="monthly",
            start_date=date(2026, 12, 1),
            end_date=date(2026, 11, 1),
            original_amount=Decimal("100"),
        )


def test_recurring_bill_rejects_discount_above_total():
    with pytest.raises(ValidationError):
        RecurringBillCreate(
            title="電費",
            frequency="monthly",
            start_date=date(2026, 11, 1),
            original_amount=Decimal("100"),
            discount_amount=Decimal("101"),
        )


def test_recurring_bill_update_rejects_unknown_frequency_and_empty_payload():
    with pytest.raises(ValidationError):
        RecurringBillUpdate(frequency="daily")
    with pytest.raises(ValidationError):
        RecurringBillUpdate()


def test_monthly_schedule_keeps_original_anchor_across_consecutive_occurrences():
    first = date(2026, 1, 31)
    second = advance_date(first, "monthly", 1, anchor_day=31)
    third = advance_date(second, "monthly", 1, anchor_day=31)
    assert second == date(2026, 2, 28)
    assert third == date(2026, 3, 31)


def test_recurring_bill_migration_permissions_match_new_family_role_catalog():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c2d4e6f8a0b1_create_recurring_bills.py"
    )
    spec = importlib.util.spec_from_file_location("g01_04_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    from app.role_catalog import DEFAULT_ROLES

    for role in DEFAULT_ROLES:
        expected = tuple(
            code for code in role["permissions"]
            if code.startswith("recurring_bills.")
        )
        assert migration.ROLE_CODES[role["name"]] == expected
        assert migration.ROLE_SCOPES[role["name"]] == role["data_scopes"]["recurring_bills"]
