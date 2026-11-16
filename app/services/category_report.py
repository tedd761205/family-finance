
"""
家庭記帳系統：分類收支統計 Service

功能：
1. 依分類統計收入及支出。
2. 支援日期區間查詢。
3. 支援收入或支出篩選。
4. 支援多幣別分開統計。
5. 計算各分類金額、筆數及占比。
6. 未分類交易列入「未分類」。
7. 排除作廢、期初餘額、信用卡繳款及轉帳本金。
8. 保留轉帳手續費支出。
9. 排除信用卡退款收入。
10. 支援 own 資料範圍。
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.category import Category
from app.models.transaction import Transaction


TAIWAN_TIMEZONE = ZoneInfo("Asia/Taipei")
ZERO = Decimal("0")


def calculate_category_summary(
    db: Session,
    family_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    transaction_type: str | None = None,
    created_by: int | None = None,
) -> dict:
    """
    計算家庭分類收支統計。

    日期使用台灣當地日期，資料庫使用 UTC。

    transaction_type:
        income：只統計收入
        expense：只統計支出
        None：同時統計
    """

    if family_id <= 0:
        raise ValueError("family_id 必須大於 0")

    if transaction_type not in (None, "income", "expense"):
        raise ValueError("transaction_type 僅允許 income 或 expense")

    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不可晚於 end_date")

    # --------------------------------------------------
    # 1. 建立台灣日期對應的 UTC 查詢區間
    # --------------------------------------------------

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

    # --------------------------------------------------
    # 2. 查詢有效交易
    # --------------------------------------------------

    query = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(
            Transaction.family_id == family_id,
            Transaction.is_voided.is_(False),
        )
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

    # --------------------------------------------------
    # 3. 查詢家庭分類及系統共用分類
    #
    # 保留停用分類，讓歷史交易仍能顯示原分類名稱。
    # --------------------------------------------------

    categories = (
        db.query(Category)
        .filter(
            or_(
                Category.family_id == family_id,
                Category.family_id.is_(None),
            )
        )
        .all()
    )

    category_map = {
        category.id: category
        for category in categories
    }

    # --------------------------------------------------
    # 4. 建立統計容器
    # --------------------------------------------------

    grouped = defaultdict(
        lambda: {
            "total_amount": ZERO,
            "transaction_count": 0,
        }
    )

    income_totals = defaultdict(lambda: ZERO)
    expense_totals = defaultdict(lambda: ZERO)

    income_count = 0
    expense_count = 0

    # --------------------------------------------------
    # 5. 逐筆計算交易
    # --------------------------------------------------

    for transaction in transactions:

        current_type = transaction.transaction_type

        # 只統計一般收入與支出
        if current_type not in ("income", "expense"):
            continue

        # 套用收入／支出篩選
        if (
            transaction_type is not None
            and current_type != transaction_type
        ):
            continue

        # 信用卡繳款交易不計入家庭收支
        if transaction.credit_card_payment_id is not None:
            continue

        # 排除信用卡帳戶的收入，例如信用卡退款
        if (
            current_type == "income"
            and transaction.account
            and transaction.account.account_type == "credit_card"
        ):
            continue

        # 排除轉帳本金
        # 轉帳手續費沒有 related_transaction_id，
        # 因此仍會保留為一般支出。
        if (
            transaction.transfer_id is not None
            and transaction.related_transaction_id is not None
        ):
            continue

        amount = Decimal(str(transaction.amount))
        currency_code = transaction.currency_code

        # --------------------------------------------------
        # 取得分類
        # --------------------------------------------------

        category = category_map.get(transaction.category_id)

        if (
            category is None
            or category.category_type != current_type
        ):
            category_id = None
            category_name = "未分類"
        else:
            category_id = category.id
            category_name = category.name

        # 分類、收支類型、幣別分開統計
        key = (
            category_id,
            category_name,
            current_type,
            currency_code,
        )

        grouped[key]["total_amount"] += amount
        grouped[key]["transaction_count"] += 1

        # --------------------------------------------------
        # 收入及支出總額
        # --------------------------------------------------

        if current_type == "income":
            income_totals[currency_code] += amount
            income_count += 1

        else:
            expense_totals[currency_code] += amount
            expense_count += 1

    # --------------------------------------------------
    # 6. 計算各分類占比
    #
    # 同一幣別、同一收支類型分開計算。
    # --------------------------------------------------

    category_items = []

    for key, values in grouped.items():

        (
            category_id,
            category_name,
            current_type,
            currency_code,
        ) = key

        amount = values["total_amount"]

        if current_type == "income":
            denominator = income_totals[currency_code]
        else:
            denominator = expense_totals[currency_code]

        if denominator > ZERO:
            percentage = (
                amount / denominator * Decimal("100")
            ).quantize(Decimal("0.01"))
        else:
            percentage = ZERO

        category_items.append(
            {
                "category_id": category_id,
                "category_name": category_name,
                "category_type": current_type,
                "currency_code": currency_code,
                "total_amount": amount,
                "transaction_count": values["transaction_count"],
                "percentage": percentage,
            }
        )

    # 金額由大到小排列
    category_items.sort(
        key=lambda item: (
            item["category_type"],
            item["currency_code"],
            -item["total_amount"],
            item["category_name"],
        )
    )

    # --------------------------------------------------
    # 7. 整理各幣別總額
    # --------------------------------------------------

    all_currencies = (
        set(income_totals.keys())
        | set(expense_totals.keys())
    )

    total_income = []
    total_expense = []
    net_amount = []

    for currency_code in sorted(all_currencies):

        income = income_totals[currency_code]
        expense = expense_totals[currency_code]

        total_income.append(
            {
                "currency_code": currency_code,
                "amount": income,
            }
        )

        total_expense.append(
            {
                "currency_code": currency_code,
                "amount": expense,
            }
        )

        net_amount.append(
            {
                "currency_code": currency_code,
                "amount": income - expense,
            }
        )

    # --------------------------------------------------
    # 8. 回傳結果
    # --------------------------------------------------

    return {
        "family_id": family_id,
        "start_date": (
            start_date.isoformat() if start_date else None
        ),
        "end_date": (
            end_date.isoformat() if end_date else None
        ),
        "transaction_type": transaction_type,
        "categories": category_items,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_amount": net_amount,
        "income_transaction_count": income_count,
        "expense_transaction_count": expense_count,
    }
