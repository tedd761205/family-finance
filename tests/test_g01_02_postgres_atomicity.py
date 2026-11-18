"""Real PostgreSQL integration tests for finance mutation atomicity.

These tests use the isolated g01_test database provisioned by GitHub Actions.
They intentionally exercise SQLAlchemy/PostgreSQL constraints and transactions,
not FakeDB query doubles.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, engine
from app import models  # noqa: F401
from app.models.account import Account
from app.models.audit_log import AuditLog
from app.models.credit_card_payment import CreditCardPayment
from app.models.family import Family
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.models.user import User
from app.routers.credit_card_payment import create_payment_transactions
from app.routers.transfer import create_transfer_transactions
from app.services.audit_log import add_audit_log


@pytest.fixture(scope="session", autouse=True)
def postgres_schema():
    if engine is None:
        pytest.fail("DATABASE_URL must point to the isolated PostgreSQL test database")

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def seed_family_accounts(db: Session):
    suffix = uuid4().hex
    user = User(
        email=f"g0102-{suffix}@example.test",
        display_name="G-01-02 PostgreSQL Test",
        is_active=True,
    )
    family = Family(name=f"G-01-02 {suffix}", currency="TWD")
    db.add_all([user, family])
    db.flush()

    source = Account(
        family_id=family.id,
        name="測試來源帳戶",
        account_type="bank",
        currency_code="TWD",
        is_active=True,
        created_by=user.id,
    )
    target = Account(
        family_id=family.id,
        name="測試目標帳戶",
        account_type="bank",
        currency_code="TWD",
        is_active=True,
        created_by=user.id,
    )
    credit_card = Account(
        family_id=family.id,
        name="測試信用卡",
        account_type="credit_card",
        currency_code="TWD",
        is_active=True,
        created_by=user.id,
    )
    db.add_all([source, target, credit_card])
    db.flush()
    return user, family, source, target, credit_card


def test_transfer_and_audit_log_commit_atomically():
    with Session(engine) as db:
        user, family, source, target, _ = seed_family_accounts(db)
        transfer = Transfer(
            family_id=family.id,
            from_account_id=source.id,
            to_account_id=target.id,
            amount=Decimal("1234.5678"),
            currency_code="TWD",
            transfer_date=datetime.now(timezone.utc),
            description="PostgreSQL atomic transfer",
            fee_amount=Decimal("0"),
            created_by=user.id,
        )
        db.add(transfer)
        db.flush()

        create_transfer_transactions(db, transfer)
        add_audit_log(
            db,
            family_id=family.id,
            actor_user_id=user.id,
            action="create",
            entity_type="transfer",
            entity_id=transfer.id,
            new_values={"amount": transfer.amount},
        )
        db.commit()

        transactions = db.scalars(
            select(Transaction).where(Transaction.transfer_id == transfer.id)
        ).all()
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "transfer",
                AuditLog.entity_id == transfer.id,
            )
        )

        assert len(transactions) == 2
        assert {item.transaction_type for item in transactions} == {"expense", "income"}
        assert transactions[0].amount == Decimal("1234.5678")
        assert audit is not None
        assert audit.new_values["amount"] == "1234.5678"


def test_transfer_and_audit_log_rollback_together_on_audit_fk_failure():
    with Session(engine) as db:
        user, family, source, target, _ = seed_family_accounts(db)
        transfer = Transfer(
            family_id=family.id,
            from_account_id=source.id,
            to_account_id=target.id,
            amount=Decimal("88.0000"),
            currency_code="TWD",
            transfer_date=datetime.now(timezone.utc),
            description="Must roll back",
            fee_amount=Decimal("0"),
            created_by=user.id,
        )
        db.add(transfer)
        db.flush()
        transfer_id = transfer.id

        create_transfer_transactions(db, transfer)
        add_audit_log(
            db,
            family_id=family.id + 999999,
            actor_user_id=user.id,
            action="create",
            entity_type="transfer",
            entity_id=transfer.id,
        )

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        assert db.scalar(
            select(func.count()).select_from(Transfer).where(Transfer.id == transfer_id)
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.transfer_id == transfer_id
            )
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.entity_type == "transfer",
                AuditLog.entity_id == transfer_id,
            )
        ) == 0


def test_credit_card_payment_and_audit_log_commit_atomically():
    with Session(engine) as db:
        user, family, source, _, credit_card = seed_family_accounts(db)
        payment = CreditCardPayment(
            family_id=family.id,
            from_account_id=source.id,
            credit_card_account_id=credit_card.id,
            amount=Decimal("987.6543"),
            currency_code="TWD",
            payment_date=datetime.now(timezone.utc),
            description="PostgreSQL atomic card payment",
            created_by=user.id,
        )
        db.add(payment)
        db.flush()

        create_payment_transactions(db, payment)
        add_audit_log(
            db,
            family_id=family.id,
            actor_user_id=user.id,
            action="create",
            entity_type="credit_card_payment",
            entity_id=payment.id,
            new_values={"amount": payment.amount},
        )
        db.commit()

        transactions = db.scalars(
            select(Transaction).where(
                Transaction.credit_card_payment_id == payment.id
            )
        ).all()
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == "credit_card_payment",
                AuditLog.entity_id == payment.id,
            )
        )

        assert len(transactions) == 2
        assert {item.transaction_type for item in transactions} == {"expense", "income"}
        assert all(item.amount == Decimal("987.6543") for item in transactions)
        assert audit is not None
        assert audit.new_values["amount"] == "987.6543"


def test_credit_card_payment_and_audit_log_rollback_together_on_audit_fk_failure():
    with Session(engine) as db:
        user, family, source, _, credit_card = seed_family_accounts(db)
        payment = CreditCardPayment(
            family_id=family.id,
            from_account_id=source.id,
            credit_card_account_id=credit_card.id,
            amount=Decimal("456.0000"),
            currency_code="TWD",
            payment_date=datetime.now(timezone.utc),
            description="Must roll back",
            created_by=user.id,
        )
        db.add(payment)
        db.flush()
        payment_id = payment.id

        create_payment_transactions(db, payment)
        add_audit_log(
            db,
            family_id=family.id + 999999,
            actor_user_id=user.id,
            action="create",
            entity_type="credit_card_payment",
            entity_id=payment.id,
        )

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        assert db.scalar(
            select(func.count()).select_from(CreditCardPayment).where(
                CreditCardPayment.id == payment_id
            )
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(Transaction).where(
                Transaction.credit_card_payment_id == payment_id
            )
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.entity_type == "credit_card_payment",
                AuditLog.entity_id == payment_id,
            )
        ) == 0



def test_account_balance_uses_real_postgresql_aggregates_and_ignores_voided_rows():
    from app.services.account_balance import calculate_account_balance

    with Session(engine) as db:
        user, family, source, _, _ = seed_family_accounts(db)
        now = datetime.now(timezone.utc)
        db.add_all([
            Transaction(
                family_id=family.id, account_id=source.id,
                transaction_type="opening_balance", amount=Decimal("100.0000"),
                currency_code="TWD", transaction_date=now, created_by=user.id,
            ),
            Transaction(
                family_id=family.id, account_id=source.id,
                transaction_type="income", amount=Decimal("20.2500"),
                currency_code="TWD", transaction_date=now, created_by=user.id,
            ),
            Transaction(
                family_id=family.id, account_id=source.id,
                transaction_type="expense", amount=Decimal("10.1250"),
                currency_code="TWD", transaction_date=now, created_by=user.id,
            ),
            Transaction(
                family_id=family.id, account_id=source.id,
                transaction_type="expense", amount=Decimal("500.0000"),
                currency_code="TWD", transaction_date=now, created_by=user.id,
                is_voided=True,
            ),
        ])
        db.commit()

        result = calculate_account_balance(db, source)

        assert result["opening_balance"] == Decimal("100.0000")
        assert result["total_income"] == Decimal("20.2500")
        assert result["total_expense"] == Decimal("10.1250")
        assert result["balance"] == Decimal("110.1250")
        assert result["transaction_count"] == 3


def test_credit_card_balance_uses_real_postgresql_aggregates():
    from app.services.account_balance import calculate_account_balance

    with Session(engine) as db:
        user, family, _, _, credit_card = seed_family_accounts(db)
        now = datetime.now(timezone.utc)
        db.add_all([
            Transaction(
                family_id=family.id, account_id=credit_card.id,
                transaction_type="opening_balance", amount=Decimal("100.0000"),
                currency_code="TWD", transaction_date=now, created_by=user.id,
            ),
            Transaction(
                family_id=family.id, account_id=credit_card.id,
                transaction_type="expense", amount=Decimal("30.0000"),
                currency_code="TWD", transaction_date=now, created_by=user.id,
            ),
            Transaction(
                family_id=family.id, account_id=credit_card.id,
                transaction_type="income", amount=Decimal("20.0000"),
                currency_code="TWD", transaction_date=now, created_by=user.id,
            ),
        ])
        db.commit()

        result = calculate_account_balance(db, credit_card)

        assert result["balance"] == Decimal("110.0000")
        assert result["transaction_count"] == 3


def seed_permission_fixture(db: Session):
    """建立真實 PostgreSQL 家庭成員、角色與權限資料。"""
    from app.models.family_member import FamilyMember
    from app.models.member_role import MemberRole
    from app.models.permission import Permission
    from app.models.role import Role
    from app.models.role_permission import RolePermission
    from app.models.role_data_scope import RoleDataScope

    user, family, *_ = seed_family_accounts(db)
    member = FamilyMember(
        family_id=family.id,
        user_id=user.id,
        status="active",
    )
    role = Role(
        family_id=family.id,
        name=f"測試角色-{uuid4().hex}",
        is_system=False,
        is_active=True,
    )
    permission = Permission(
        code=f"g01_02.test.{uuid4().hex}",
        name="G-01-02 測試權限",
        category="test",
        is_active=True,
    )
    db.add_all([member, role, permission])
    db.flush()
    db.add_all([
        MemberRole(
            family_member_id=member.id,
            role_id=role.id,
            family_id=family.id,
        ),
        RolePermission(
            role_id=role.id,
            permission_id=permission.id,
        ),
        RoleDataScope(
            role_id=role.id,
            family_id=family.id,
            resource="transactions",
            scope="own",
        ),
    ])
    db.flush()
    return user, family, member, role, permission


def test_permission_service_accepts_active_member_with_assigned_permission():
    from app.dependencies.permissions import require_permission

    with Session(engine) as db:
        user, family, member, role, permission = seed_permission_fixture(db)
        db.commit()

        found_member, roles = require_permission(
            db, user.id, family.id, permission.code
        )

        assert found_member.id == member.id
        assert [item.id for item in roles] == [role.id]


def test_permission_service_denies_inactive_family_member():
    from app.dependencies.permissions import require_permission
    from app.models.family_member import FamilyMember

    with Session(engine) as db:
        user, family, member, _, permission = seed_permission_fixture(db)
        member.status = "left"
        db.commit()

        with pytest.raises(PermissionError, match="有效成員"):
            require_permission(db, user.id, family.id, permission.code)


def test_permission_service_denies_inactive_user():
    from app.dependencies.permissions import require_permission

    with Session(engine) as db:
        user, family, _, _, permission = seed_permission_fixture(db)
        user.is_active = False
        db.commit()

        with pytest.raises(PermissionError, match="未啟用"):
            require_permission(db, user.id, family.id, permission.code)


def test_permission_service_denies_permission_not_assigned_to_member_role():
    from app.dependencies.permissions import require_permission
    from app.models.permission import Permission

    with Session(engine) as db:
        user, family, _, _, _ = seed_permission_fixture(db)
        unassigned = Permission(
            code=f"g01_02.unassigned.{uuid4().hex}",
            name="未指派權限",
            category="test",
            is_active=True,
        )
        db.add(unassigned)
        db.commit()

        with pytest.raises(PermissionError, match="沒有執行此操作的權限"):
            require_permission(db, user.id, family.id, unassigned.code)


def test_permission_service_denies_inactive_permission():
    from app.dependencies.permissions import require_permission

    with Session(engine) as db:
        user, family, _, _, permission = seed_permission_fixture(db)
        permission.is_active = False
        db.commit()

        with pytest.raises(PermissionError, match="沒有執行此操作的權限"):
            require_permission(db, user.id, family.id, permission.code)


def test_postgresql_data_scope_prefers_family_over_own_across_roles():
    from app.dependencies.permissions import get_data_scope
    from app.models.member_role import MemberRole
    from app.models.role import Role
    from app.models.role_data_scope import RoleDataScope

    with Session(engine) as db:
        user, family, member, own_role, _ = seed_permission_fixture(db)
        family_role = Role(
            family_id=family.id,
            name=f"家庭範圍角色-{uuid4().hex}",
            is_system=False,
            is_active=True,
        )
        db.add(family_role)
        db.flush()
        db.add_all([
            MemberRole(
                family_member_id=member.id,
                role_id=family_role.id,
                family_id=family.id,
            ),
            RoleDataScope(
                role_id=family_role.id,
                family_id=family.id,
                resource="transactions",
                scope="family",
            ),
        ])
        db.commit()

        from app.dependencies.permissions import get_active_family_roles
        roles = get_active_family_roles(db, member.id, family.id)

        assert {role.id for role in roles} == {own_role.id, family_role.id}
        assert get_data_scope(db, roles, family.id, "transactions") == "family"
