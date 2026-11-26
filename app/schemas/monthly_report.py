
"""
家庭記帳系統：月份報表 Schema
"""

from datetime import date
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


class MonthlyDailyReportRow(BaseModel):
    """月份內單日、單一幣別的收支明細。"""

    report_date: date = Field(
        ...,
        description="台灣當地日期，序列化格式 YYYY-MM-DD",
    )
    currency_code: str = Field(..., min_length=3, max_length=3)
    total_income: Decimal = Field(..., description="當日總收入")
    total_expense: Decimal = Field(..., description="當日總支出")
    net_amount: Decimal = Field(..., description="當日淨收支")
    transaction_count: int = Field(..., ge=0, description="納入收支統計的交易筆數")


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

    daily_reports: list[MonthlyDailyReportRow] = Field(
        default_factory=list,
        description="依台灣日期及幣別分組的每日收支明細，日期格式 YYYY-MM-DD",
    )

    total_income: list[MonthlyReportAmount]

    total_expense: list[MonthlyReportAmount]

    net_amount: list[MonthlyReportAmount]

    transaction_count: int = Field(
        ...,
        ge=0,
        description="納入當月收支統計的交易筆數；與每日明細筆數合計一致",
    )
