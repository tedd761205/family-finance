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


# ---------------------------------------------------------------------------
# FastAPI + JWT + PostgreSQL integration tests
# ---------------------------------------------------------------------------

def _seed_api_permission_catalog(db: Session):
    """為家庭 API 整合測試建立預設角色所需的系統權限。"""
    from app.models.permission import Permission
    from app.role_catalog import DEFAULT_ROLES

    required_codes = sorted({
        code
        for role_config in DEFAULT_ROLES
        for code in role_config["permissions"]
    })
    existing_codes = {
        row[0]
        for row in db.query(Permission.code)
        .filter(Permission.code.in_(required_codes))
        .all()
    }
    for code in required_codes:
        if code not in existing_codes:
            db.add(Permission(
                code=code,
                name=code,
                category=code.split(".", 1)[0],
                is_active=True,
            ))
    db.flush()


@pytest.fixture
def api_client(monkeypatch):
    """使用真正 PostgreSQL、JWT 與 FastAPI 路由的測試用戶端。"""
    from fastapi.testclient import TestClient
    from main import app
    from app.database import get_db

    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "g01-02-api-integration-test-secret-key-32-bytes-minimum",
    )

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _register_and_login(client, email: str, display_name: str):
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "G01-02-test-password-123!",
            "display_name": display_name,
        },
    )
    assert registered.status_code == 201, registered.text

    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "G01-02-test-password-123!",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return registered.json(), {"Authorization": f"Bearer {token}"}


def test_api_register_login_and_me_require_valid_jwt(api_client):
    suffix = uuid4().hex
    user, headers = _register_and_login(
        api_client,
        f"api-auth-{suffix}@example.test",
        "API 認證測試",
    )

    assert "password_hash" not in user
    assert api_client.get("/auth/me").status_code == 401

    response = api_client.get("/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == user["id"]
    assert response.json()["email"] == user["email"]
    assert "password_hash" not in response.json()


def test_api_family_create_and_list_are_bound_to_authenticated_user(api_client):
    suffix = uuid4().hex
    user, headers = _register_and_login(
        api_client,
        f"api-family-{suffix}@example.test",
        "家庭建立測試",
    )

    with Session(engine) as db:
        _seed_api_permission_catalog(db)
        db.commit()

    created = api_client.post(
        "/families",
        headers=headers,
        json={"name": f"API 測試家庭 {suffix}", "currency": "TWD"},
    )
    assert created.status_code == 201, created.text
    family_data = created.json()
    assert family_data["user_id"] == user["id"]
    assert family_data["admin_role_name"] == "家庭管理員"

    listed = api_client.get("/families/mine", headers=headers)
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["families"][0]["family_id"] == family_data["family_id"]

    unauthenticated = api_client.get("/families/mine")
    assert unauthenticated.status_code == 401


def test_api_family_invite_assigns_default_role_and_rejects_duplicate(api_client):
    suffix = uuid4().hex
    _, owner_headers = _register_and_login(
        api_client,
        f"api-owner-{suffix}@example.test",
        "家庭管理員測試",
    )
    invited_user, _ = _register_and_login(
        api_client,
        f"api-invitee-{suffix}@example.test",
        "受邀成員測試",
    )

    with Session(engine) as db:
        _seed_api_permission_catalog(db)
        db.commit()

    created = api_client.post(
        "/families",
        headers=owner_headers,
        json={"name": f"邀請測試家庭 {suffix}", "currency": "TWD"},
    )
    assert created.status_code == 201, created.text
    family_id = created.json()["family_id"]

    invited = api_client.post(
        f"/families/{family_id}/members",
        headers=owner_headers,
        json={"email": invited_user["email"]},
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["user_id"] == invited_user["id"]
    assert invited.json()["role_name"] == "一般成員"
    assert invited.json()["status"] == "active"

    duplicate = api_client.post(
        f"/families/{family_id}/members",
        headers=owner_headers,
        json={"email": invited_user["email"]},
    )
    assert duplicate.status_code == 409


def test_api_non_member_cannot_invite_into_another_users_family(api_client):
    suffix = uuid4().hex
    _, owner_headers = _register_and_login(
        api_client,
        f"api-owner-isolation-{suffix}@example.test",
        "家庭擁有者",
    )
    _, outsider_headers = _register_and_login(
        api_client,
        f"api-outsider-{suffix}@example.test",
        "非家庭成員",
    )
    invitee, _ = _register_and_login(
        api_client,
        f"api-target-{suffix}@example.test",
        "受邀目標",
    )

    with Session(engine) as db:
        _seed_api_permission_catalog(db)
        db.commit()

    created = api_client.post(
        "/families",
        headers=owner_headers,
        json={"name": f"隔離測試家庭 {suffix}", "currency": "TWD"},
    )
    assert created.status_code == 201, created.text
    family_id = created.json()["family_id"]

    denied = api_client.post(
        f"/families/{family_id}/members",
        headers=outsider_headers,
        json={"email": invitee["email"]},
    )
    assert denied.status_code == 403
