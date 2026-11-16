
"""
家庭記帳系統：分類收支統計 Schema
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
        description="該類型總金額中的占比百分比",
    )


class CategoryReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family_id: int = Field(
        ...,
        gt=0,
    )

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

    total_income: Decimal = Field(
        ...,
        description="總收入",
    )

    total_expense: Decimal = Field(
        ...,
        description="總支出",
    )

    net_amount: Decimal = Field(
        ...,
        description="淨收支",
    )

    income_transaction_count: int = Field(
        ...,
        ge=0,
        description="收入交易筆數",
    )

    expense_transaction_count: int = Field(
        ...,
        ge=0,
        description="支出交易筆數",
    )
