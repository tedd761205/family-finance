
"""
家庭記帳系統：家庭收支統計服務

功能：
1. 計算家庭收入。
2. 計算家庭支出。
3. 排除自有帳戶轉帳本金。
4. 保留轉帳手續費支出。
5. 排除信用卡繳款。
6. 排除信用卡退款收入。
7. 排除已作廢交易。
8. 依幣別分開統計。

會計規則：
- 一般收入：計入家庭收入。
- 一般支出：計入家庭支出。
- 信用卡刷卡：計入家庭支出。
- 信用卡繳款：不計入家庭收支。
- 信用卡退款：不計入家庭收入。
- 轉帳本金：不計入家庭收支。
- 轉帳手續費：計入家庭支出。
- 期初餘額：不計入家庭收入或支出。
"""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from app.models.transaction import Transaction


ZERO = Decimal("0.0000")


def calculate_household_summary(
    db: Session,
    family_id: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    """
    計算指定家庭的收入與支出統計。

    start_date：起始時間，包含該時間。
    end_date：結束時間，包含該時間。

    不同幣別分開計算，不進行匯率換算。
    """

    if start_date is not None and end_date is not None:
        if start_date > end_date:
            raise ValueError("開始日期不可晚於結束日期")

    query = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(
            Transaction.family_id == family_id,
            Transaction.is_voided.is_(False),
        )
    )

    if start_date is not None:
        query = query.filter(
            Transaction.transaction_date >= start_date,
        )

    if end_date is not None:
        query = query.filter(
            Transaction.transaction_date <= end_date,
        )

    transactions = query.all()

    income_by_currency = defaultdict(lambda: ZERO)
    expense_by_currency = defaultdict(lambda: ZERO)

    for transaction in transactions:

        amount = Decimal(transaction.amount)
        currency = transaction.currency_code

        # ------------------------------------------------
        # 期初餘額不屬於當期收入或支出
        # ------------------------------------------------

        if transaction.transaction_type == "opening_balance":
            continue

        # ------------------------------------------------
        # 信用卡繳款不計入家庭收支
        # ------------------------------------------------

        if transaction.credit_card_payment_id is not None:
            continue

        # ------------------------------------------------
        # 轉帳處理
        # ------------------------------------------------

        if transaction.transfer_id is not None:

            # 轉帳本金有 related_transaction_id，
            # 轉帳手續費沒有 related_transaction_id。
            #
            # 只將手續費 expense 計入家庭支出。

            if (
                transaction.related_transaction_id is None
                and transaction.transaction_type == "expense"
            ):
                expense_by_currency[currency] += amount

            continue

        # ------------------------------------------------
        # 一般收入
        # ------------------------------------------------

        if transaction.transaction_type == "income":

            account = transaction.account

            # 信用卡退款會記錄在信用卡帳戶，
            # 但不能算家庭收入。
            if account is not None and account.account_type == "credit_card":
                continue

            income_by_currency[currency] += amount

        # ------------------------------------------------
        # 一般支出（包含信用卡刷卡）
        # ------------------------------------------------

        elif transaction.transaction_type == "expense":
            expense_by_currency[currency] += amount

    # ----------------------------------------------------
    # 整理各幣別統計結果
    # ----------------------------------------------------

    currencies = sorted(
        set(income_by_currency.keys())
        | set(expense_by_currency.keys())
    )

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

    return {
        "family_id": family_id,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_amount": net_amount,
        "transaction_count": len(transactions),
    }
