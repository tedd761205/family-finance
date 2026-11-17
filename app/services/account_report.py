
"""
家庭記帳系統：帳戶收支統計與明細 Service

功能：
1. 依帳戶統計收入及支出。
2. 統計帳戶轉入與轉出。
3. 獨立統計信用卡繳款。
4. 獨立統計信用卡退款。
5. 支援台灣日期區間查詢。
6. 支援 own 資料範圍。
7. 排除作廢交易及期初餘額（收支統計）。
8. 查詢帳戶交易明細。
9. 支援交易明細分頁。
10. 顯示帳戶期初餘額及目前餘額。
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.transaction import Transaction
from app.services.account_balance import calculate_account_balance


TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")
ZERO = Decimal("0.0000")


def get_account_or_raise(
    db: Session,
    family_id: int,
    account_id: int,
) -> Account:
    """取得指定家庭的有效帳戶。"""

    if family_id <= 0:
        raise ValueError("family_id 必須大於 0")

    if account_id <= 0:
        raise ValueError("account_id 必須大於 0")

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

    return account


def get_taiwan_date_range(
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[datetime | None, datetime | None]:
    """將台灣日期區間轉換為 UTC 起訖時間。"""

    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不可晚於 end_date")

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

    return start_datetime, end_datetime


def build_account_transaction_query(
    db: Session,
    family_id: int,
    account_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    created_by: int | None = None,
):
    """建立帳戶交易明細查詢。"""

    account = get_account_or_raise(
        db=db,
        family_id=family_id,
        account_id=account_id,
    )

    start_datetime, end_datetime = get_taiwan_date_range(
        start_date=start_date,
        end_date=end_date,
    )

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

    return account, query


def calculate_account_summary(
    db: Session,
    family_id: int,
    account_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    created_by: int | None = None,
) -> dict:
    """
    計算指定帳戶的收支統計及目前餘額。

    created_by:
        None：統計整個家庭
        整數：只統計指定使用者建立的交易

    注意：
        opening_balance 和 current_balance
        使用完整帳戶有效交易計算，不受報表日期區間影響。

        期間收入、支出及其他統計仍依照日期區間及資料範圍計算。
    """

    account, query = build_account_transaction_query(
        db=db,
        family_id=family_id,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        created_by=created_by,
    )

    transactions = query.all()

    # 使用共用帳戶餘額服務，確保餘額公式一致。
    balance_data = calculate_account_balance(
        db=db,
        account=account,
    )

    opening_balance = balance_data["opening_balance"]
    current_balance = balance_data["balance"]

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

        if transaction_type == "opening_balance":
            continue

        if transaction.credit_card_payment_id is not None:
            credit_card_payment_count += 1

            if transaction_type == "income":
                credit_card_payment_in += amount

            elif transaction_type == "expense":
                credit_card_payment_out += amount

            continue

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

        if transaction_type == "income":

            if account.account_type == "credit_card":
                credit_card_refund_amount += amount
                credit_card_refund_count += 1
                continue

            total_income += amount
            income_count += 1

        elif transaction_type == "expense":
            total_expense += amount
            expense_count += 1

    return {
        "family_id": family_id,
        "account_id": account.id,
        "account_name": account.name,
        "account_type": account.account_type,
        "currency_code": account.currency_code,

        # 帳戶餘額
        "opening_balance": opening_balance,
        "current_balance": current_balance,

        # 報表日期
        "start_date": (
            start_date.isoformat() if start_date else None
        ),
        "end_date": (
            end_date.isoformat() if end_date else None
        ),

        # 期間收支
        "total_income": total_income,
        "total_expense": total_expense,
        "net_amount": total_income - total_expense,

        # 轉帳
        "transfer_in_amount": transfer_in_amount,
        "transfer_out_amount": transfer_out_amount,

        # 信用卡繳款
        "credit_card_payment_in": credit_card_payment_in,
        "credit_card_payment_out": credit_card_payment_out,

        # 信用卡退款
        "credit_card_refund_amount": credit_card_refund_amount,

        # 交易筆數
        "income_transaction_count": income_count,
        "expense_transaction_count": expense_count,
        "transfer_in_count": transfer_in_count,
        "transfer_out_count": transfer_out_count,
        "credit_card_payment_count": credit_card_payment_count,
        "credit_card_refund_count": credit_card_refund_count,
        "transaction_count": len(transactions),
    }


def calculate_account_transactions(
    db: Session,
    family_id: int,
    account_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 20,
    created_by: int | None = None,
) -> dict:
    """
    查詢指定帳戶的交易明細。

    日期使用台灣當地日期。
    資料庫使用 UTC。

    作廢交易不列入明細。

    期初餘額保留在明細中，方便查閱帳戶建立時的餘額。

    created_by:
        None：查詢整個家庭
        整數：只查詢指定使用者建立的交易
    """

    if page < 1:
        raise ValueError("page 必須大於或等於 1")

    if page_size < 1:
        raise ValueError("page_size 必須大於或等於 1")

    if page_size > 100:
        raise ValueError("page_size 不可大於 100")

    account, query = build_account_transaction_query(
        db=db,
        family_id=family_id,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        created_by=created_by,
    )

    total_count = query.count()

    transactions = (
        query
        .order_by(
            Transaction.transaction_date.desc(),
            Transaction.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

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
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "transactions": transactions,
    }
