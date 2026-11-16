
"""
家庭記帳系統：家庭收支統計服務

功能：
1. 計算家庭收入。
2. 計算家庭支出。
3. 排除自有帳戶轉帳。
4. 保留轉帳手續費支出。
5. 排除信用卡繳款與信用卡退款收入。
6. 排除已作廢交易。
7. 依幣別分開統計。

統計原則：
- 一般收入：計入家庭收入。
- 一般支出：計入家庭支出。
- 信用卡刷卡：計入家庭支出。
- 信用卡繳款：不計入家庭收支。
- 信用卡退款：不計入家庭收入。
- 轉帳本金：不計入家庭收支。
- 轉帳手續費：計入家庭支出。
"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.transaction import Transaction


ZERO = Decimal("0.0000")


def calculate_household_summary(
    db: Session,
    family_id: int,
    start_date=None,
    end_date=None,
):
    """
    計算指定家庭的收支統計。

    日期條件：
    start_date：起始時間（包含）
    end_date：結束時間（包含）

    回傳：
    {
        "family_id": 1,
        "total_income": [...],
        "total_expense": [...],
        "net_amount": [...]
    }

    不同幣別分開計算，不進行匯率換算。
    """

    query = db.query(Transaction).filter(
        Transaction.family_id == family_id,
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

    transactions = query.all()

    income_by_currency = defaultdict(lambda: ZERO)
    expense_by_currency = defaultdict(lambda: ZERO)

    for transaction in transactions:
        amount = Decimal(transaction.amount)
        currency = transaction.currency_code

        # ----------------------------------------------------
        # 轉帳交易
        # ----------------------------------------------------

        if transaction.transfer_id is not None:

            # 轉帳本金：排除。
            # 轉帳手續費：沒有 related_transaction_id，
            # 且交易類型為 expense，因此保留支出。
            if (
                transaction.related_transaction_id is None
                and transaction.transaction_type == "expense"
            ):
                expense_by_currency[currency] += amount

            continue

        # ----------------------------------------------------
        # 信用卡繳款交易
        # ----------------------------------------------------

        if transaction.credit_card_payment_id is not None:
            continue

        # ----------------------------------------------------
        # 一般收入
        # ----------------------------------------------------

        if transaction.transaction_type == "income":

            # 信用卡退款目前使用 credit_card 帳戶的 income
            # 記錄，不能算家庭收入。
            if transaction.account.account_type == "credit_card":
                continue

            income_by_currency[currency] += amount

        # ----------------------------------------------------
        # 一般支出（包含信用卡刷卡）
        # ----------------------------------------------------

        elif transaction.transaction_type == "expense":
            expense_by_currency[currency] += amount

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
