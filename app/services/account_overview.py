
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.account import Account
from app.services.account_balance import calculate_account_balance


ZERO = Decimal("0.0000")

ASSET_ACCOUNT_TYPES = {
    "bank",
    "cash",
    "e_payment",
}


def calculate_account_overview(
    db: Session,
    family_id: int,
    active_only: bool = True,
) -> dict:
    """
    計算家庭帳戶總覽。

    功能：
    1. 查詢家庭帳戶。
    2. 計算每個帳戶的目前餘額。
    3. 區分資產帳戶與信用卡負債。
    4. 依幣別分組統計。
    5. 可選擇只查詢啟用中的帳戶。
    """

    query = db.query(Account).filter(
        Account.family_id == family_id
    )

    if active_only:
        query = query.filter(Account.is_active.is_(True))

    accounts = query.order_by(Account.id.asc()).all()

    currency_data = defaultdict(
        lambda: {
            "total_asset_balance": ZERO,
            "total_credit_card_debt": ZERO,
            "account_count": 0,
            "asset_account_count": 0,
            "credit_card_count": 0,
        }
    )

    account_items = []

    for account in accounts:
        balance_data = calculate_account_balance(
            db=db,
            account=account,
        )

        currency_code = account.currency_code
        balance = balance_data["balance"]

        summary = currency_data[currency_code]
        summary["account_count"] += 1

        if account.account_type in ASSET_ACCOUNT_TYPES:
            summary["total_asset_balance"] += balance
            summary["asset_account_count"] += 1

        elif account.account_type == "credit_card":
            summary["total_credit_card_debt"] += balance
            summary["credit_card_count"] += 1

        account_items.append(
            {
                "account_id": account.id,
                "account_name": account.name,
                "account_type": account.account_type,
                "currency_code": account.currency_code,
                "institution_name": account.institution_name,
                "account_number_last4": (
                    account.account_number_last4
                ),
                "credit_limit": account.credit_limit,
                "opening_balance": balance_data["opening_balance"],
                "total_income": balance_data["total_income"],
                "total_expense": balance_data["total_expense"],
                "current_balance": balance,
                "transaction_count": balance_data[
                    "transaction_count"
                ],
                "is_active": account.is_active,
            }
        )

    currency_summaries = []

    for currency_code in sorted(currency_data.keys()):
        summary = currency_data[currency_code]

        total_asset_balance = summary[
            "total_asset_balance"
        ]

        total_credit_card_debt = summary[
            "total_credit_card_debt"
        ]

        currency_summaries.append(
            {
                "currency_code": currency_code,
                "total_asset_balance": total_asset_balance,
                "total_credit_card_debt": total_credit_card_debt,
                "net_position": (
                    total_asset_balance - total_credit_card_debt
                ),
                "account_count": summary["account_count"],
                "asset_account_count": summary[
                    "asset_account_count"
                ],
                "credit_card_count": summary[
                    "credit_card_count"
                ],
            }
        )

    return {
        "family_id": family_id,
        "active_only": active_only,
        "account_count": len(account_items),
        "accounts": account_items,
        "currency_summaries": currency_summaries,
    }
