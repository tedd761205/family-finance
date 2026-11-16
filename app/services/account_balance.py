
"""
家庭記帳系統：帳戶餘額計算服務

功能：
1. 計算單一帳戶目前餘額。
2. 排除已作廢交易。
3. 支援銀行、現金、電子支付及信用卡。
4. 支援期初餘額。
5. 信用卡正數代表欠款。

計算規則：

一般資產帳戶：
期初餘額 + 收入 - 支出

信用卡帳戶：
期初欠款 + 刷卡支出 - 繳款及退款

注意：
- 不直接儲存餘額。
- 只使用有效交易即時計算。
- 轉帳及信用卡繳款透過其關聯交易反映帳戶餘額。
- 不同幣別由不同帳戶分別計算。
"""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.transaction import Transaction


ZERO = Decimal("0.0000")


def calculate_account_balance(
    db: Session,
    account: Account,
) -> dict:
    """
    計算單一帳戶餘額。

    Args:
        db: SQLAlchemy Session
        account: 已確認家庭歸屬的帳戶

    Returns:
        dict: 餘額及交易統計資料
    """

    rows = (
        db.query(
            Transaction.transaction_type,
            func.coalesce(
                func.sum(Transaction.amount),
                0,
            ).label("total_amount"),
            func.count(Transaction.id).label("transaction_count"),
        )
        .filter(
            Transaction.family_id == account.family_id,
            Transaction.account_id == account.id,
            Transaction.is_voided.is_(False),
        )
        .group_by(
            Transaction.transaction_type,
        )
        .all()
    )

    totals = {
        "opening_balance": ZERO,
        "income": ZERO,
        "expense": ZERO,
    }

    transaction_count = 0

    for row in rows:
        transaction_type = row.transaction_type

        amount = Decimal(
            str(row.total_amount or 0)
        )

        if transaction_type in totals:
            totals[transaction_type] = amount

        transaction_count += row.transaction_count

    opening_balance = totals["opening_balance"]
    total_income = totals["income"]
    total_expense = totals["expense"]

    if account.account_type == "credit_card":
        # 信用卡：正數代表欠款
        balance = (
            opening_balance
            + total_expense
            - total_income
        )

    else:
        # 銀行、現金、電子支付：正數代表資產
        balance = (
            opening_balance
            + total_income
            - total_expense
        )

    return {
        "account_id": account.id,
        "family_id": account.family_id,
        "account_name": account.name,
        "account_type": account.account_type,
        "currency_code": account.currency_code,
        "opening_balance": opening_balance,
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": balance,
        "transaction_count": transaction_count,
    }
