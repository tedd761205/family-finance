
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AccountOverviewItem(BaseModel):
    """單一帳戶總覽"""

    model_config = ConfigDict(from_attributes=True)

    account_id: int
    account_name: str
    account_type: str
    currency_code: str

    institution_name: Optional[str] = None
    account_number_last4: Optional[str] = None

    credit_limit: Optional[Decimal] = None

    opening_balance: Decimal
    total_income: Decimal
    total_expense: Decimal
    current_balance: Decimal

    transaction_count: int
    is_active: bool


class AccountOverviewCurrencySummary(BaseModel):
    """依幣別統計帳戶資產與信用卡負債"""

    currency_code: str

    total_asset_balance: Decimal
    total_credit_card_debt: Decimal
    net_position: Decimal

    account_count: int
    asset_account_count: int
    credit_card_count: int


class AccountOverviewResponse(BaseModel):
    """家庭帳戶總覽回應"""

    family_id: int

    active_only: bool

    account_count: int

    accounts: list[AccountOverviewItem]

    currency_summaries: list[AccountOverviewCurrencySummary]
