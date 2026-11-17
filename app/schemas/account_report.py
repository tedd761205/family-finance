
"""
家庭記帳系統：帳戶收支統計 Schema
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountReportAmount(BaseModel):
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


class AccountReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    family_id: int = Field(..., gt=0)

    account_id: int = Field(..., gt=0)

    account_name: str = Field(
        ...,
        description="帳戶名稱",
    )

    account_type: str = Field(
        ...,
        description="帳戶類型",
    )

    currency_code: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="帳戶幣別",
    )

    start_date: str | None = Field(
        default=None,
        description="統計開始日期，台灣當地日期",
    )

    end_date: str | None = Field(
        default=None,
        description="統計結束日期，台灣當地日期",
    )

    total_income: Decimal = Field(
        default=Decimal("0"),
        description="一般收入總額",
    )

    total_expense: Decimal = Field(
        default=Decimal("0"),
        description="一般支出總額",
    )

    net_amount: Decimal = Field(
        default=Decimal("0"),
        description="一般收支淨額",
    )

    transfer_in_amount: Decimal = Field(
        default=Decimal("0"),
        description="轉入金額",
    )

    transfer_out_amount: Decimal = Field(
        default=Decimal("0"),
        description="轉出金額",
    )

    credit_card_payment_in: Decimal = Field(
        default=Decimal("0"),
        description="信用卡繳款入帳金額",
    )

    credit_card_payment_out: Decimal = Field(
        default=Decimal("0"),
        description="信用卡繳款支出金額",
    )

    income_transaction_count: int = Field(
        default=0,
        ge=0,
        description="一般收入筆數",
    )

    expense_transaction_count: int = Field(
        default=0,
        ge=0,
        description="一般支出筆數",
    )

    transfer_in_count: int = Field(
        default=0,
        ge=0,
        description="轉入筆數",
    )

    transfer_out_count: int = Field(
        default=0,
        ge=0,
        description="轉出筆數",
    )

    credit_card_payment_count: int = Field(
        default=0,
        ge=0,
        description="信用卡繳款筆數",
    )

    transaction_count: int = Field(
        default=0,
        ge=0,
        description="統計期間內有效交易筆數，包含特殊交易",
    )
