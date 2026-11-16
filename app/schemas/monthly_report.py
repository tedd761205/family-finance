
"""
家庭記帳系統：月份報表 Schema
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MonthlyReportAmount(BaseModel):
    """單一幣別的月份統計金額"""

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


class MonthlyReportResponse(BaseModel):
    """家庭月份收支報表回應"""

    model_config = ConfigDict(from_attributes=True)

    family_id: int = Field(
        ...,
        gt=0,
    )

    year: int = Field(
        ...,
        ge=2000,
        le=2100,
    )

    month: int = Field(
        ...,
        ge=1,
        le=12,
    )

    total_income: list[MonthlyReportAmount]

    total_expense: list[MonthlyReportAmount]

    net_amount: list[MonthlyReportAmount]

    transaction_count: int = Field(
        ...,
        ge=0,
        description="當月有效交易筆數",
    )
