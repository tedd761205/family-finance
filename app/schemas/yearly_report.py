
"""
家庭記帳系統：年度收支報表 Schema
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class YearlyReportAmount(BaseModel):
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


class YearlyReportMonth(BaseModel):
    month: int = Field(
        ...,
        ge=1,
        le=12,
        description="月份",
    )

    total_income: list[YearlyReportAmount] = Field(
        ...,
        description="當月總收入",
    )

    total_expense: list[YearlyReportAmount] = Field(
        ...,
        description="當月總支出",
    )

    net_amount: list[YearlyReportAmount] = Field(
        ...,
        description="當月淨收支",
    )

    transaction_count: int = Field(
        ...,
        ge=0,
        description="當月有效交易筆數",
    )


class YearlyReportResponse(BaseModel):
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

    monthly_reports: list[YearlyReportMonth] = Field(
        ...,
        description="1 至 12 月的每月收支統計",
    )

    total_income: list[YearlyReportAmount] = Field(
        ...,
        description="全年總收入",
    )

    total_expense: list[YearlyReportAmount] = Field(
        ...,
        description="全年總支出",
    )

    net_amount: list[YearlyReportAmount] = Field(
        ...,
        description="全年淨收支",
    )

    transaction_count: int = Field(
        ...,
        ge=0,
        description="全年有效交易筆數",
    )
