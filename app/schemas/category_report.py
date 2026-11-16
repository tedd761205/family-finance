
"""
家庭記帳系統：分類收支統計 Schema
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CategoryReportAmount(BaseModel):
    currency_code: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="幣別代碼",
    )

    amount: Decimal = Field(
        ...,
        description="統計金額",
    )


class CategoryReportItem(BaseModel):
    category_id: int | None = Field(
        default=None,
        description="分類 ID，未分類時為 null",
    )

    category_name: str = Field(
        ...,
        description="分類名稱",
    )

    category_type: Literal["income", "expense"] = Field(
        ...,
        description="分類類型",
    )

    currency_code: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="幣別代碼",
    )

    total_amount: Decimal = Field(
        ...,
        description="該分類統計金額",
    )

    transaction_count: int = Field(
        ...,
        ge=0,
        description="該分類交易筆數",
    )

    percentage: Decimal = Field(
        ...,
        ge=0,
        le=100,
        description="同幣別、同收支類型中的占比百分比",
    )


class CategoryReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family_id: int = Field(..., gt=0)

    start_date: str | None = Field(
        default=None,
        description="統計開始日期，台灣當地日期",
    )

    end_date: str | None = Field(
        default=None,
        description="統計結束日期，台灣當地日期",
    )

    transaction_type: Literal["income", "expense"] | None = Field(
        default=None,
        description="收入或支出；null 表示同時統計",
    )

    categories: list[CategoryReportItem] = Field(
        ...,
        description="分類統計明細",
    )

    total_income: list[CategoryReportAmount] = Field(
        default_factory=list,
        description="各幣別總收入",
    )

    total_expense: list[CategoryReportAmount] = Field(
        default_factory=list,
        description="各幣別總支出",
    )

    net_amount: list[CategoryReportAmount] = Field(
        default_factory=list,
        description="各幣別淨收支",
    )

    income_transaction_count: int = Field(
        default=0,
        ge=0,
        description="收入交易筆數",
    )

    expense_transaction_count: int = Field(
        default=0,
        ge=0,
        description="支出交易筆數",
    )
