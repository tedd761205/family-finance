
"""
家庭記帳系統：每日收支報表 Service

功能：
1. 計算指定日期的家庭收入。
2. 計算指定日期的家庭支出。
3. 計算指定日期的淨收支。
4. 支援不同幣別分開統計。
5. 使用台灣日期轉換 UTC 查詢。
6. 支援 own / family 資料範圍。
7. 排除作廢交易、期初餘額及不應重複計算的交易。
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.models.transaction import Transaction


TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")


def calculate_daily_summary(
    db: Session,
    family_id: int,
    report_date: date,
    created_by: int | None = None,
):
    """
    計算指定日期的家庭收支報表。

    Args:
        db: SQLAlchemy Session
        family_id: 家庭 ID
        report_date: 台灣當地日期
        created_by: 若指定，只統計該使用者建立的交易

    Returns:
        每日收支統計資料
    """

    if family_id <= 0:
        raise ValueError("family_id 必須大於 0")

    if not isinstance(report_date, date):
        raise ValueError("report_date 必須是有效日期")

    # 台灣當地日期的起始時間
    start_local = datetime.combine(
        report_date,
        time.min,
    ).replace(tzinfo=TAIWAN_TIMEZONE)

    # 下一天的起始時間
    end_local = datetime.combine(
        report_date + timedelta(days=1),
        time.min,
    ).replace(tzinfo=TAIWAN_TIMEZONE)

    # 轉換為 UTC
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    query = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(
            Transaction.family_id == family_id,
            Transaction.is_voided.is_(False),
            Transaction.transaction_date >= start_utc,
            Transaction.transaction_date < end_utc,
        )
    )

    # own 資料範圍
    if created_by is not None:
        query = query.filter(
            Transaction.created_by == created_by
        )

    transactions = query.all()

    income_by_currency = defaultdict(Decimal)
    expense_by_currency = defaultdict(Decimal)

    for transaction in transactions:

        transaction_type = transaction.transaction_type
        amount = Decimal(transaction.amount)
        currency_code = transaction.currency_code

        # 期初餘額不計入每日收支
        if transaction_type == "opening_balance":
            continue

        # 信用卡繳款的兩筆交易均排除
        if transaction.credit_card_payment_id is not None:
            continue

        # 轉帳交易只計入手續費支出
        if transaction.transfer_id is not None:

            is_transfer_fee = (
                transaction.related_transaction_id is None
                and transaction_type == "expense"
            )

            if is_transfer_fee:
                expense_by_currency[currency_code] += amount

            continue

        # 一般收入
        if transaction_type == "income":

            # 信用卡退款不計入家庭收入
            if (
                transaction.account is not None
                and transaction.account.account_type == "credit_card"
            ):
                continue

            income_by_currency[currency_code] += amount

        # 一般支出，包含信用卡消費
        elif transaction_type == "expense":
            expense_by_currency[currency_code] += amount

    # 整合所有出現過的幣別
    currencies = sorted(
        set(income_by_currency.keys())
        | set(expense_by_currency.keys())
    )

    total_income = []
    total_expense = []
    net_amount = []

    for currency_code in currencies:

        income = income_by_currency[currency_code]
        expense = expense_by_currency[currency_code]

        total_income.append({
            "currency_code": currency_code,
            "amount": income,
        })

        total_expense.append({
            "currency_code": currency_code,
            "amount": expense,
        })

        net_amount.append({
            "currency_code": currency_code,
            "amount": income - expense,
        })

    return {
        "family_id": family_id,
        "report_date": report_date.isoformat(),
        "total_income": total_income,
        "total_expense": total_expense,
        "net_amount": net_amount,
        "transaction_count": len(transactions),
    }
