from datetime import timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.routers.bank_import import (
    _fingerprint,
    _parse_amount,
    _parse_date,
    _parse_type,
    _read_csv,
)
from main import app


def test_import_date_parser_supports_iso_and_common_bank_formats():
    iso = _parse_date("2026-11-19")
    slash = _parse_date("2026/11/19")
    compact = _parse_date("20261119")
    roc = _parse_date("115/11/19")
    assert iso.tzinfo is not None
    assert iso == slash == compact == roc
    assert iso.astimezone(timezone.utc).hour == 16


def test_import_amount_parser_handles_negative_and_parentheses():
    assert _parse_amount("1,234.5000") == (Decimal("1234.5000"), False)
    assert _parse_amount("-88.25") == (Decimal("88.25"), True)
    assert _parse_amount("(NT$ 50.00)") == (Decimal("50.00"), True)
    with pytest.raises(ValueError, match="大於 0"):
        _parse_amount("0")
    with pytest.raises(ValueError, match="小數 4 位"):
        _parse_amount("1.00001")


def test_import_type_parser_uses_bank_debit_credit_labels_or_amount_sign():
    assert _parse_type("", True) == "expense"
    assert _parse_type("", False) == "income"
    assert _parse_type("借方", False) == "expense"
    assert _parse_type("貸方", True) == "income"
    assert _parse_type("D", False) == "expense"
    assert _parse_type("C", True) == "income"
    with pytest.raises(ValueError, match="交易類型"):
        _parse_type("transfer", False)


def test_import_fingerprint_is_stable_and_account_scoped():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    dt = datetime(2026, 11, 19, tzinfo=ZoneInfo("Asia/Taipei"))
    first = _fingerprint(1, dt, "expense", Decimal("100.00"), "TWD", "交通", "REF-1")
    same = _fingerprint(1, dt, "expense", Decimal("100.00"), "TWD", "其他說明", "REF-1")
    other_account = _fingerprint(2, dt, "expense", Decimal("100.00"), "TWD", "交通", "REF-1")
    assert first == same
    assert first != other_account


def test_import_csv_reader_supports_utf8_and_cp950_and_detects_duplicate_headers():
    headers, rows = _read_csv("日期,金額,摘要\n2026-11-19,-100,交通\n".encode("utf-8"))
    assert headers == ["日期", "金額", "摘要"]
    assert rows[0]["摘要"] == "交通"
    headers, rows = _read_csv("日期,金額,摘要\n2026/11/19,200,薪資\n".encode("cp950"))
    assert rows[0]["摘要"] == "薪資"
    with pytest.raises(Exception):
        _read_csv("日期,日期\n2026-11-19,2026-11-20\n".encode("utf-8"))


def test_bank_import_routes_are_registered():
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
    assert "/imports/inspect" in schema["paths"]
    assert "/imports/batches" in schema["paths"]
    assert "/imports/batches/{batch_id}/confirm" in schema["paths"]
    assert "/imports/batches/{batch_id}/void" in schema["paths"]
