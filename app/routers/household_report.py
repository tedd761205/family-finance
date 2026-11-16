
"""
家庭記帳系統：家庭收支報表 API

功能：
1. 查詢家庭收支統計。
2. 支援指定日期區間。
3. 支援不同幣別分開統計。
4. 套用家庭權限。
5. 套用 own / family 資料範圍。
"""

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)
from app.models.user import User
from app.models.transaction import Transaction
from app.services.household_report import (
    calculate_household_summary,
)
from app.schemas.household_report import (
    HouseholdReportResponse,
)


router = APIRouter(
    prefix="/reports",
    tags=["Household Reports"],
)


def check_report_permission(
    db: Session,
    user_id: int,
    family_id: int,
):
    try:
        return require_permission(
            db=db,
            user_id=user_id,
            family_id=family_id,
            permission_code="reports.view",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


def check_report_scope(
    db: Session,
    roles: list,
    family_id: int,
):
    try:
        return require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="transactions",
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


@router.get(
    "/household-summary",
    response_model=HouseholdReportResponse,
    summary="查詢家庭收支統計",
)
def get_household_summary(
    family_id: int = Query(..., gt=0),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # ----------------------------------------------------
    # 權限檢查
    # ----------------------------------------------------

    _, roles = check_report_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
    )

    scope = check_report_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    # ----------------------------------------------------
    # 日期驗證
    # ----------------------------------------------------

    if (
        start_date is not None
        and end_date is not None
        and start_date > end_date
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="開始日期不可晚於結束日期",
        )

    # ----------------------------------------------------
    # 取得統計資料
    # ----------------------------------------------------

    try:
        result = calculate_household_summary(
            db=db,
            family_id=family_id,
            start_date=start_date,
            end_date=end_date,
        )

        # ------------------------------------------------
        # own 資料範圍
        # ------------------------------------------------

        if scope == "own":
            query = db.query(Transaction).filter(
                Transaction.family_id == family_id,
                Transaction.created_by == current_user.id,
                Transaction.is_voided.is_(False),
            )

            if start_date is not None:
                query = query.filter(
                    Transaction.transaction_date >= start_date,
                )

            if end_date is not None:
                query = query.filter(
                    Transaction.transaction_date <= end_date,
                )

            own_transactions = query.all()

            # own 範圍需重新使用相同統計規則。
            from collections import defaultdict
            from decimal import Decimal

            income_by_currency = defaultdict(
                lambda: Decimal("0.0000")
            )
            expense_by_currency = defaultdict(
                lambda: Decimal("0.0000")
            )

            for transaction in own_transactions:

                if transaction.transaction_type == "opening_balance":
                    continue

                if transaction.credit_card_payment_id is not None:
                    continue

                amount = Decimal(transaction.amount)
                currency = transaction.currency_code

                if transaction.transfer_id is not None:
                    if (
                        transaction.related_transaction_id is None
                        and transaction.transaction_type == "expense"
                    ):
                        expense_by_currency[currency] += amount
                    continue

                if transaction.transaction_type == "income":
                    if (
                        transaction.account.account_type
                        == "credit_card"
                    ):
                        continue

                    income_by_currency[currency] += amount

                elif transaction.transaction_type == "expense":
                    expense_by_currency[currency] += amount

            currencies = sorted(
                set(income_by_currency)
                | set(expense_by_currency)
            )

            result = {
                "family_id": family_id,
                "total_income": [
                    {
                        "currency_code": currency,
                        "amount": income_by_currency[currency],
                    }
                    for currency in currencies
                ],
                "total_expense": [
                    {
                        "currency_code": currency,
                        "amount": expense_by_currency[currency],
                    }
                    for currency in currencies
                ],
                "net_amount": [
                    {
                        "currency_code": currency,
                        "amount": (
                            income_by_currency[currency]
                            - expense_by_currency[currency]
                        ),
                    }
                    for currency in currencies
                ],
                "transaction_count": len(own_transactions),
            }

        result["start_date"] = (
            start_date.isoformat()
            if start_date is not None
            else None
        )

        result["end_date"] = (
            end_date.isoformat()
            if end_date is not None
            else None
        )

        return result

    except HTTPException:
        raise

    except Exception:
        raise
