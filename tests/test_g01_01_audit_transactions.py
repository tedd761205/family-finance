"""Real PostgreSQL transaction tests for business data and AuditLog atomicity."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models.account import Account
from app.models.audit_log import AuditLog
from app.models.family import Family
from app.models.user import User
from app.services.audit_log import add_audit_log


TEST_TABLES = [
    Family.__table__,
    User.__table__,
    Account.__table__,
    AuditLog.__table__,
]


@pytest.fixture(scope="module", autouse=True)
def postgres_test_schema():
    """Create only the tables needed by these isolated integration tests."""
    if engine is None or SessionLocal is None:
        pytest.fail("DATABASE_URL must point to the PostgreSQL test service")

    Base.metadata.create_all(bind=engine, tables=TEST_TABLES)
    yield
    Base.metadata.drop_all(bind=engine, tables=TEST_TABLES)
    engine.dispose()


@pytest.fixture
def db_session():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _create_family_and_user(db: Session):
    suffix = uuid4().hex
    family = Family(name=f"Audit transaction test {suffix}")
    user = User(
        email=f"audit-test-{suffix}@example.invalid",
        display_name="Audit Test",
        is_active=True,
    )
    db.add_all([family, user])
    db.commit()
    db.refresh(family)
    db.refresh(user)
    return family, user


def _new_account(family_id: int, user_id: int) -> Account:
    return Account(
        family_id=family_id,
        name="Atomicity test account",
        account_type="bank",
        currency_code="TWD",
        credit_limit=Decimal("12345.6700"),
        created_by=user_id,
    )


def test_business_record_and_audit_log_commit_together(db_session: Session):
    family, user = _create_family_and_user(db_session)
    account = _new_account(family.id, user.id)
    db_session.add(account)
    db_session.flush()

    audit = add_audit_log(
        db_session,
        family_id=family.id,
        actor_user_id=user.id,
        action="create",
        entity_type="account",
        entity_id=account.id,
        new_values={"credit_limit": Decimal("12345.6700")},
        description="PostgreSQL atomic commit test",
    )

    db_session.commit()

    persisted_account = (
        db_session.query(Account)
        .filter(Account.id == account.id)
        .one()
    )
    persisted_audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.id == audit.id)
        .one()
    )

    assert persisted_account.credit_limit == Decimal("12345.6700")
    assert persisted_audit.entity_id == persisted_account.id
    assert persisted_audit.new_values == {"credit_limit": "12345.6700"}


def test_rollback_removes_business_record_and_audit_log_together(
    db_session: Session,
):
    family, user = _create_family_and_user(db_session)
    account = _new_account(family.id, user.id)
    db_session.add(account)
    db_session.flush()

    add_audit_log(
        db_session,
        family_id=family.id,
        actor_user_id=user.id,
        action="create",
        entity_type="account",
        entity_id=account.id,
        new_values={"name": account.name},
        description="PostgreSQL rollback test",
    )

    db_session.rollback()

    account_count = (
        db_session.query(func.count(Account.id))
        .filter(Account.family_id == family.id)
        .scalar()
    )
    audit_count = (
        db_session.query(func.count(AuditLog.id))
        .filter(AuditLog.family_id == family.id)
        .scalar()
    )

    assert account_count == 0
    assert audit_count == 0


def test_audit_insert_failure_rolls_back_business_record(db_session: Session):
    family, user = _create_family_and_user(db_session)
    account = _new_account(family.id, user.id)
    db_session.add(account)
    db_session.flush()

    # Deliberately use a non-existent family FK to make the audit INSERT fail.
    add_audit_log(
        db_session,
        family_id=9_223_372_036_854_770_000,
        actor_user_id=user.id,
        action="create",
        entity_type="account",
        entity_id=account.id,
        new_values={"name": account.name},
        description="Intentional FK failure test",
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()

    account_count = (
        db_session.query(func.count(Account.id))
        .filter(Account.family_id == family.id)
        .scalar()
    )
    audit_count = (
        db_session.query(func.count(AuditLog.id))
        .filter(AuditLog.family_id == family.id)
        .scalar()
    )

    assert account_count == 0
    assert audit_count == 0
