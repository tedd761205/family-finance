
"""
家庭記帳系統：帳戶餘額 API Schema

用途：
1. 單一帳戶餘額回應。
2. 家庭帳戶餘額列表回應。
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountBalanceResponse(BaseModel):
    """單一帳戶餘額回應。"""

    model_config = ConfigDict(
        from_attributes=True,
    )

    account_id: int
    family_id: int
    account_name: str
    account_type: str
    currency_code: str

    opening_balance: Decimal
    total_income: Decimal
    total_expense: Decimal
    balance: Decimal

    transaction_count: int


class AccountBalanceListResponse(BaseModel):
    """家庭帳戶餘額列表回應。"""

    success: bool = True
    total: int
    balances: list[AccountBalanceResponse]
