
"""
家庭記帳系統：家庭收支報表 Schema
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class HouseholdReportAmount(BaseModel):
    """單一幣別的統計金額"""

    currency_code: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="幣別代碼，例如 TWD、USD",
    )

    amount: Decimal = Field(
        ...,
        description="統計金額",
    )


class HouseholdReportResponse(BaseModel):
    """家庭收支報表回應"""

    model_config = ConfigDict(from_attributes=True)

    family_id: int

    start_date: str | None = None

    end_date: str | None = None

    total_income: list[HouseholdReportAmount]

    total_expense: list[HouseholdReportAmount]

    net_amount: list[HouseholdReportAmount]

    transaction_count: int = Field(
        ...,
        ge=0,
        description="統計期間內有效交易筆數（包含不納入收支的交易）",
    )
