
"""
家庭記帳系統：年度收支報表 Service

功能：
1. 統計全年 1 至 12 月收入。
2. 統計全年 1 至 12 月支出。
3. 計算每月淨收支。
4. 計算全年總收入、總支出及淨收支。
5. 支援不同幣別分開統計。
6. 使用台灣時區計算年度範圍。
7. 支援 own / family 資料範圍。
8. 排除作廢交易、期初餘額及不應重複計算的交易。
"""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.models.transaction import Transaction


TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")


def calculate_yearly_summary(
    db: Session,
    family_id: int,
    year: int,
    created_by: int | None = None,
):
    """
    計算指定年度的家庭收支報表。

    Args:
        db: SQLAlchemy Session
        family_id: 家庭 ID
        year: 年份
        created_by: 若指定，只統計該使用者建立的交易

    Returns:
        年度收支統計資料
    """

    if family_id <= 0:
        raise ValueError("family_id 必須大於 0")

    if year < 2000 or year > 2100:
        raise ValueError("年份必須介於 2000 至 2100")

    # 台灣年度起始時間
    start_local = datetime(
        year,
        1,
        1,
        0,
        0,
        0,
        tzinfo=TAIWAN_TIMEZONE,
    )

    # 下一年度起始時間
    end_local = datetime(
        year + 1,
        1,
        1,
        0,
        0,
        0,
        tzinfo=TAIWAN_TIMEZONE,
    )

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

    # 每月收入及支出
    monthly_income = defaultdict(
        lambda: defaultdict(Decimal)
    )

    monthly_expense = defaultdict(
        lambda: defaultdict(Decimal)
    )

    # 全年收入及支出
    yearly_income = defaultdict(Decimal)
    yearly_expense = defaultdict(Decimal)

    for transaction in transactions:

        transaction_type = transaction.transaction_type
        amount = Decimal(transaction.amount)
        currency_code = transaction.currency_code

        # 取得台灣當地月份
        transaction_local = (
            transaction.transaction_date
            .replace(tzinfo=timezone.utc)
            .astimezone(TAIWAN_TIMEZONE)
        )

        month = transaction_local.month

        # 期初餘額不計入收支
        if transaction_type == "opening_balance":
            continue

        # 信用卡繳款不計入家庭收支
        if transaction.credit_card_payment_id is not None:
            continue

        # 轉帳只計入手續費
        if transaction.transfer_id is not None:

            is_transfer_fee = (
                transaction.related_transaction_id is None
                and transaction_type == "expense"
            )

            if is_transfer_fee:
                monthly_expense[month][currency_code] += amount
                yearly_expense[currency_code] += amount

            continue

        # 一般收入
        if transaction_type == "income":

            # 信用卡退款不計入家庭收入
            if (
                transaction.account is not None
                and transaction.account.account_type == "credit_card"
            ):
                continue

            monthly_income[month][currency_code] += amount
            yearly_income[currency_code] += amount

        # 一般支出，包含信用卡消費
        elif transaction_type == "expense":

            monthly_expense[month][currency_code] += amount
            yearly_expense[currency_code] += amount

    # 所有出現過的幣別
    currencies = sorted(
        set(yearly_income.keys())
        | set(yearly_expense.keys())
    )

    monthly_reports = []

    # 固定輸出 1 至 12 月
    for month in range(1, 13):

        month_currencies = sorted(
            set(monthly_income[month].keys())
            | set(monthly_expense[month].keys())
        )

        total_income = []
        total_expense = []
        net_amount = []

        for currency_code in month_currencies:

            income = monthly_income[month][currency_code]
            expense = monthly_expense[month][currency_code]

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

        # 計算當月交易筆數
        month_transaction_count = sum(
            1
            for transaction in transactions
            if (
                transaction.transaction_date
                .replace(tzinfo=timezone.utc)
                .astimezone(TAIWAN_TIMEZONE)
                .month == month
            )
        )

        monthly_reports.append({
            "month": month,
            "total_income": total_income,
            "total_expense": total_expense,
            "net_amount": net_amount,
            "transaction_count": month_transaction_count,
        })

    # 全年合計
    total_income = []
    total_expense = []
    net_amount = []

    for currency_code in currencies:

        income = yearly_income[currency_code]
        expense = yearly_expense[currency_code]

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
        "year": year,
        "monthly_reports": monthly_reports,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_amount": net_amount,
        "transaction_count": len(transactions),
    }
