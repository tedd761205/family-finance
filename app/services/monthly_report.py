
"""
家庭記帳系統：月份收支報表統計服務

功能：
1. 依照指定年月統計家庭收入。
2. 依照指定年月統計家庭支出。
3. 計算收支淨額。
4. 支援不同幣別分開統計。
5. 排除作廢交易。
6. 排除期初餘額、信用卡繳款及內部轉帳本金。
7. 轉帳手續費仍計入家庭支出。
8. 排除信用卡退款收入。
9. 支援 own / family 資料範圍。
10. 使用台灣時區計算月份，再轉換為 UTC 查詢。
"""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from app.models.transaction import Transaction


ZERO = Decimal("0.0000")

TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")


def calculate_monthly_summary(
    db: Session,
    family_id: int,
    year: int,
    month: int,
    created_by: int | None = None,
):
    """
    計算指定家庭、指定月份的收支統計。

    Args:
        db:
            SQLAlchemy Session。

        family_id:
            家庭 ID。

        year:
            西元年份。

        month:
            月份，1 至 12。

        created_by:
            若指定，只統計該使用者建立的交易。
            None 表示統計整個家庭。

    Returns:
        dict:
            家庭月份收支統計。
    """

    # --------------------------------------------------
    # 1. 驗證年月
    # --------------------------------------------------

    if year < 2000 or year > 2100:
        raise ValueError("年份必須介於 2000 至 2100")

    if month < 1 or month > 12:
        raise ValueError("月份必須介於 1 至 12")

    # --------------------------------------------------
    # 2. 建立台灣時間月份區間
    # --------------------------------------------------

    start_local = datetime(
        year,
        month,
        1,
        0,
        0,
        0,
        tzinfo=TAIWAN_TIMEZONE,
    )

    if month == 12:
        end_local = datetime(
            year + 1,
            1,
            1,
            0,
            0,
            0,
            tzinfo=TAIWAN_TIMEZONE,
        )
    else:
        end_local = datetime(
            year,
            month + 1,
            1,
            0,
            0,
            0,
            tzinfo=TAIWAN_TIMEZONE,
        )

    # 轉換為 UTC，資料庫日期以 UTC 儲存。
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    # --------------------------------------------------
    # 3. 查詢有效交易
    # --------------------------------------------------

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

    # own 資料範圍：只查詢自己建立的交易。
    if created_by is not None:
        query = query.filter(
            Transaction.created_by == created_by,
        )

    transactions = query.all()

    # --------------------------------------------------
    # 4. 初始化各幣別統計
    # --------------------------------------------------

    income_by_currency = defaultdict(
        lambda: ZERO
    )

    expense_by_currency = defaultdict(
        lambda: ZERO
    )

    # 每日明細依台灣當地日期及幣別分組；不把不同幣別合併。
    daily_by_date_currency = defaultdict(
        lambda: {
            "income": ZERO,
            "expense": ZERO,
            "transaction_count": 0,
        }
    )

    # --------------------------------------------------
    # 5. 逐筆計算
    # --------------------------------------------------

    for transaction in transactions:

        transaction_type = transaction.transaction_type

        amount = Decimal(transaction.amount)

        currency = transaction.currency_code

        # ----------------------------------------------
        # 排除期初餘額
        # ----------------------------------------------

        if transaction_type == "opening_balance":
            continue

        # ----------------------------------------------
        # 排除信用卡繳款交易
        # ----------------------------------------------

        if transaction.credit_card_payment_id is not None:
            continue

        # ----------------------------------------------
        # 處理內部轉帳
        # ----------------------------------------------

        if transaction.transfer_id is not None:

            # 只有沒有關聯交易的轉帳支出，
            # 才是轉帳手續費。
            if (
                transaction.related_transaction_id is None
                and transaction_type == "expense"
            ):
                expense_by_currency[currency] += amount
                if transaction.transaction_date is not None:
                    transaction_datetime = transaction.transaction_date
                    if transaction_datetime.tzinfo is None:
                        transaction_datetime = transaction_datetime.replace(tzinfo=timezone.utc)
                    local_date = transaction_datetime.astimezone(TAIWAN_TIMEZONE).date()
                    daily = daily_by_date_currency[(local_date, currency)]
                    daily["expense"] += amount
                    daily["transaction_count"] += 1

            # 轉帳本金不計入家庭收入或支出。
            continue

        # ----------------------------------------------
        # 一般收入
        # ----------------------------------------------

        if transaction_type == "income":

            account = transaction.account

            # 信用卡退款不算家庭收入。
            if (
                account is not None
                and account.account_type == "credit_card"
            ):
                continue

            income_by_currency[currency] += amount
            if transaction.transaction_date is not None:
                transaction_datetime = transaction.transaction_date
                if transaction_datetime.tzinfo is None:
                    transaction_datetime = transaction_datetime.replace(tzinfo=timezone.utc)
                local_date = transaction_datetime.astimezone(TAIWAN_TIMEZONE).date()
                daily = daily_by_date_currency[(local_date, currency)]
                daily["income"] += amount
                daily["transaction_count"] += 1

        # ----------------------------------------------
        # 一般支出
        # ----------------------------------------------

        elif transaction_type == "expense":

            expense_by_currency[currency] += amount
            if transaction.transaction_date is not None:
                transaction_datetime = transaction.transaction_date
                if transaction_datetime.tzinfo is None:
                    transaction_datetime = transaction_datetime.replace(tzinfo=timezone.utc)
                local_date = transaction_datetime.astimezone(TAIWAN_TIMEZONE).date()
                daily = daily_by_date_currency[(local_date, currency)]
                daily["expense"] += amount
                daily["transaction_count"] += 1

    # --------------------------------------------------
    # 6. 整理幣別
    # --------------------------------------------------

    currencies = sorted(
        set(income_by_currency.keys())
        | set(expense_by_currency.keys())
    )

    # --------------------------------------------------
    # 7. 組合回傳結果
    # --------------------------------------------------

    total_income = []
    total_expense = []
    net_amount = []

    for currency in currencies:

        income = income_by_currency[currency]

        expense = expense_by_currency[currency]

        total_income.append({
            "currency_code": currency,
            "amount": income,
        })

        total_expense.append({
            "currency_code": currency,
            "amount": expense,
        })

        net_amount.append({
            "currency_code": currency,
            "amount": income - expense,
        })

    daily_reports = [
        {
            "report_date": report_date.isoformat(),
            "currency_code": currency,
            "total_income": values["income"],
            "total_expense": values["expense"],
            "net_amount": values["income"] - values["expense"],
            "transaction_count": values["transaction_count"],
        }
        for (report_date, currency), values in sorted(daily_by_date_currency.items())
    ]

    return {
        "family_id": family_id,
        "year": year,
        "month": month,
        "daily_reports": daily_reports,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_amount": net_amount,
        "transaction_count": len(transactions),
    }
