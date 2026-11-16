
"""
家庭記帳系統：每日收支報表 Schema
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailyReportAmount(BaseModel):
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


class DailyReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family_id: int = Field(
        ...,
        gt=0,
    )

    report_date: str = Field(
        ...,
        description="報表日期，台灣當地日期 YYYY-MM-DD",
    )

    total_income: list[DailyReportAmount] = Field(
        ...,
        description="當日總收入",
    )

    total_expense: list[DailyReportAmount] = Field(
        ...,
        description="當日總支出",
    )

    net_amount: list[DailyReportAmount] = Field(
        ...,
        description="當日淨收支",
    )

    transaction_count: int = Field(
        ...,
        ge=0,
        description="當日有效交易筆數",
    )
