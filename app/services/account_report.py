
"""
家庭記帳系統：帳戶收支統計 Service

功能：
1. 依帳戶統計收入及支出。
2. 統計帳戶轉入與轉出。
3. 獨立統計信用卡繳款。
4. 獨立統計信用卡退款。
5. 支援台灣日期區間查詢。
6. 支援 own 資料範圍。
7. 排除作廢交易及期初餘額。
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.transaction import Transaction


TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")
ZERO = Decimal("0")


def calculate_account_summary(
    db: Session,
    family_id: int,
    account_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    created_by: int | None = None,
) -> dict:
    """
    計算指定帳戶的收支統計。

    日期使用台灣當地日期，資料庫使用 UTC。

    created_by:
        None：統計整個家庭
        整數：只統計指定使用者建立的交易
    """

    if family_id <= 0:
        raise ValueError("family_id 必須大於 0")

    if account_id <= 0:
        raise ValueError("account_id 必須大於 0")

    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不可晚於 end_date")

    account = (
        db.query(Account)
        .filter(
            Account.id == account_id,
            Account.family_id == family_id,
            Account.is_active.is_(True),
        )
        .first()
    )

    if account is None:
        raise ValueError("找不到指定帳戶或帳戶已停用")

    start_datetime = None
    end_datetime = None

    if start_date:
        start_datetime = datetime.combine(
            start_date,
            time.min,
            tzinfo=TAIWAN_TIMEZONE,
        ).astimezone(timezone.utc)

    if end_date:
        end_datetime = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=TAIWAN_TIMEZONE,
        ).astimezone(timezone.utc)

    query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
        Transaction.account_id == account_id,
        Transaction.is_voided.is_(False),
    )

    if start_datetime:
        query = query.filter(
            Transaction.transaction_date >= start_datetime
        )

    if end_datetime:
        query = query.filter(
            Transaction.transaction_date < end_datetime
        )

    if created_by is not None:
        query = query.filter(
            Transaction.created_by == created_by
        )

    transactions = query.all()

    total_income = ZERO
    total_expense = ZERO

    transfer_in_amount = ZERO
    transfer_out_amount = ZERO

    credit_card_payment_in = ZERO
    credit_card_payment_out = ZERO

    credit_card_refund_amount = ZERO

    income_count = 0
    expense_count = 0

    transfer_in_count = 0
    transfer_out_count = 0

    credit_card_payment_count = 0
    credit_card_refund_count = 0

    for transaction in transactions:
        transaction_type = transaction.transaction_type
        amount = Decimal(str(transaction.amount))

        # 期初餘額不列入期間收支
        if transaction_type == "opening_balance":
            continue

        # 信用卡繳款
        if transaction.credit_card_payment_id is not None:
            credit_card_payment_count += 1

            if transaction_type == "income":
                credit_card_payment_in += amount

            elif transaction_type == "expense":
                credit_card_payment_out += amount

            continue

        # 轉帳本金
        if (
            transaction.transfer_id is not None
            and transaction.related_transaction_id is not None
        ):
            if transaction_type == "income":
                transfer_in_amount += amount
                transfer_in_count += 1

            elif transaction_type == "expense":
                transfer_out_amount += amount
                transfer_out_count += 1

            continue

        # 一般收入
        if transaction_type == "income":

            # 信用卡帳戶收入視為退款，不列入一般收入
            if account.account_type == "credit_card":
                credit_card_refund_amount += amount
                credit_card_refund_count += 1
                continue

            total_income += amount
            income_count += 1

        # 一般支出，包括轉帳手續費
        elif transaction_type == "expense":
            total_expense += amount
            expense_count += 1

    return {
        "family_id": family_id,
        "account_id": account.id,
        "account_name": account.name,
        "account_type": account.account_type,
        "currency_code": account.currency_code,
        "start_date": (
            start_date.isoformat() if start_date else None
        ),
        "end_date": (
            end_date.isoformat() if end_date else None
        ),
        "total_income": total_income,
        "total_expense": total_expense,
        "net_amount": total_income - total_expense,
        "transfer_in_amount": transfer_in_amount,
        "transfer_out_amount": transfer_out_amount,
        "credit_card_payment_in": credit_card_payment_in,
        "credit_card_payment_out": credit_card_payment_out,
        "credit_card_refund_amount": credit_card_refund_amount,
        "income_transaction_count": income_count,
        "expense_transaction_count": expense_count,
        "transfer_in_count": transfer_in_count,
        "transfer_out_count": transfer_out_count,
        "credit_card_payment_count": credit_card_payment_count,
        "credit_card_refund_count": credit_card_refund_count,
        "transaction_count": len(transactions),
    }
